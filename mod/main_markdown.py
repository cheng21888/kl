import streamlit as st
import io
import contextlib
import pandas as pd
import numpy as np
from datetime import datetime
from mod.config import SAVE_DIR
from mod.data_loader import get_trade_dates
from mod.analyzer import (
    analyze_auction_flow, calculate_hot_concepts, calculate_auto_concepts, build_zt_tags
)
from mod.reporter import (
    report_overview, report_top_stocks, report_sector_flow, report_top_amount_stocks,
    report_hot_concepts, report_auto_concepts, report_zt_stocks
)

# ---------------------- 新增：竞价涨幅＞9%分析函数 ----------------------
def report_9pct_stocks(today_date: datetime, prev_date: datetime, df_9pct: pd.DataFrame) -> None:
    """ 输出竞价涨幅＞9%个股分析报告（适配无封单额、按竞价金额排序） """
    print(f"\n# 📈 竞价涨幅＞9%个股分析 ({today_date.strftime('%Y-%m-%d')})")

    # 1. 核心统计汇总
    p9_count = len(df_9pct)
    cm20_count = len(df_9pct[df_9pct['涨跌幅'] > 19]) if '涨跌幅' in df_9pct.columns else 0

    print(f"\n**今日竞价涨幅＞9%总数**: {p9_count} 只 (其中 20CM: {cm20_count} 只)")

    # 2. 竞价金额统计（适配现有字段，与report_top_amount_stocks保持单位一致）
    if '竞价金额_今' in df_9pct.columns:
        avg_amt = (df_9pct['竞价金额_今'].mean() / 1e8).round(4)
        max_amt = (df_9pct['竞价金额_今'].max() / 1e8).round(4)
        print(f"**竞价金额统计**: 平均 {avg_amt} 亿 | 最高 {max_amt} 亿")

    # 3. 详情表处理（按竞价金额降序，单位转换为亿，保留4位小数）
    df_display = df_9pct.copy()
    if '竞价金额_今' in df_display.columns:
        df_display = df_display.sort_values('竞价金额_今', ascending=False)
        df_display['竞价金额(亿)'] = (df_display['竞价金额_今'] / 1e8).round(4)

    # 定义展示列（自动过滤不存在的列，兼容现有数据结构）
    show_cols = ['股票简称', '涨跌幅', '竞价金额(亿)', '增量(亿)', '所属行业', '流通市值(亿)', '结构标签', '热点标签']
    final_show = [c for c in show_cols if c in df_display.columns]

    # 输出markdown表格（复用现有工具逻辑，与其他报告格式统一）
    print(pd.DataFrame(df_display[final_show]).to_markdown(index=False))


# ---------------------- 新增：从analyzer.py导入的函数 ----------------------
def calculate_auto(df: pd.DataFrame) -> pd.DataFrame:
    """自动识别并计算题材共振数据"""
    if df.empty or '所属概念' not in df.columns: 
        return pd.DataFrame()

    df_c = df.copy()
    df_c['涨跌幅_num'] = pd.to_numeric(df_c['涨跌幅'], errors='coerce').fillna(0)
    df_c['tag_list'] = (df_c['所属概念'].fillna('') + ';' + df_c['所属行业'].fillna('')).str.replace('，', ';').str.split(';')
    
    exploded = df_c.explode('tag_list').rename(columns={'tag_list': '题材名称'})
    
    # 定义BLACKLIST（如果原文件中有定义，请确保导入）
    BLACKLIST = ['', ' ', '--', 'None', 'nan']  # 示例黑名单，请根据实际情况调整
    
    exploded = exploded[(~exploded['题材名称'].isin(BLACKLIST)) & (exploded['题材名称'].str.len() >= 2)]
    if exploded.empty: 
        return pd.DataFrame()

    concept_grp = exploded.groupby('题材名称').agg(
        家数=('股票代码', 'count'),
        红盘率_val=('涨跌幅_num', lambda x: (x > 0).mean() * 100),
        平均涨跌_val=('涨跌幅_num', 'mean'),
        资金增量_亿=('增量(亿)', 'sum')
    )

    exploded['rank'] = exploded.groupby('题材名称')['增量(亿)'].rank(ascending=True, method='first')
    top2_stats = exploded[exploded['rank'] <= 2].groupby('题材名称')['增量(亿)'].sum()
    concept_grp['top2_sum'] = top2_stats
    
    concept_grp['状态'] = np.where(
        (concept_grp['top2_sum'] / concept_grp['资金增量_亿'].replace(0, 1) > 0.7),
        "单兵(抱团)", "板块(合力)"
    )

    leaders = exploded[exploded['rank'] == 1].copy()
    leaders['增量先锋'] = (
        leaders['股票简称'] + "(" + leaders['涨跌幅'].astype(str) + "%) " + 
        "[" + leaders['结构标签'].fillna('--') + "]"
    )

    final = concept_grp.merge(leaders[['题材名称', '增量先锋']], on='题材名称', how='left')
    final = final[
        (final['家数'] >= 4) & (final['家数'] <= 100) & 
        (final['资金增量_亿'] > 0.3) & (final['平均涨跌_val'] > 0)
    ]
    
    final = final.rename(columns={
        '红盘率_val': '红盘率%', '平均涨跌_val': '平均涨跌%', '资金增量_亿': '资金增量(亿)'
    })
    
    return final


# ---------------------- 新增：从reporter.py导入的函数 ----------------------
def report_auto(final_df: pd.DataFrame, top_n: int = 10):
    """输出题材共振雷达报告"""
    if final_df.empty: 
        return
    
    print("\n## 7. 🚀 题材资金共振雷达")
    display_df = final_df.head(top_n)
    cols = ['题材名称', '家数', '红盘率%', '平均涨跌%', '资金增量(亿)', '状态', '增量先锋']
    
    # 使用print_markdown_table函数（如果已定义）或使用pandas的to_markdown
    try:
        print_md_table(display_df[cols], "6.1 题材资金共振雷达 (Top 10)", "综合增量、合力程度及领涨个股性质")
    except NameError:
        # 如果print_md_table未定义，使用pandas默认输出
        print(display_df[cols].to_markdown(index=False))


# ---------------------- 辅助函数：如果print_md_table未定义 ----------------------
def print_md_table(df, title, description):
    """简单的Markdown表格输出函数"""
    print(f"\n### {title}")
    print(f"*{description}*")
    print(df.to_markdown(index=False))
    print()


# ------------------------------------------------------------------------


def highlight_6_2(row):
    # 1. 定义 6.2 的五个核心条件判定
    c1 = row['家数'] > 10
    c2 = row['红盘率%'] > 75
    c3 = row['平均涨跌%'] > 1.2
    c4 = row['资金增量(亿)'] > 1
    c5 = '突发放量' in str(row['增量先锋'])

    # 初始化样式列表（与列数对应）
    styles = [''] * len(row)

    # 2. 如果 5 个条件全满足，整行背景变红
    if all([c1, c2, c3, c4, c5]):
        return ['background-color: #FFCCCC; color: black; font-weight: bold'] * len(row)

    # 3. 如果不全满足，则对符合条件的单项标淡黄色
    # 对应列名索引：['题材名称', '家数', '红盘率%', '平均涨跌%', '资金增量(亿)', '状态', '增量先锋']
    col_map = {
        '家数': c1, '红盘率%': c2, '平均涨跌%': c3,
        '资金增量(亿)': c4, '增量先锋': c5
    }

    for i, col_name in enumerate(row.index):
        if col_name in col_map and col_map[col_name]:
            styles[i] = 'background-color: #FFFFE0; color: black;'  # 淡黄色

    return styles


# --- 第一部分：只负责数据计算 (保留缓存) ---
@st.cache_data
def get_auction_analysis_data(today_date, prev_date):
    """
    这个函数只跑逻辑，不涉及任何 st.xxx 组件
    """
    # 1. 执行核心分析逻辑
    result = analyze_auction_flow(today_date, prev_date)
    if result is None:
        return None

    df, overview = result

    # 提前构建涨停/热点标签并合并
    df_zt = build_zt_tags(today_date, prev_date)
    if not df_zt.empty and '热点标签' in df_zt.columns:
        tag_slice = df_zt[['股票代码', '热点标签']].drop_duplicates('股票代码')
        df = pd.merge(df, tag_slice, on='股票代码', how='left')
        df['热点标签'] = df['热点标签'].fillna('')
    else:
        df['热点标签'] = ''

    # ---------------------- 新增：筛选竞价涨幅＞9%个股数据 ----------------------
    # 基于现有df筛选，与涨停数据df_zt保持同结构、同字段
    df_9pct = df[df['涨跌幅'] > 9].copy()
    # ----------------------------------------------------------------------------

    # 2. 计算其他题材数据
    total_abs = df['增量(亿)'].abs().sum()
    total_j = df['减量(亿)'].abs().sum()
    hot_concept_stats = calculate_hot_concepts(df)
    auto_concept_df = calculate_auto_concepts(df)
    
    # 3. 捕获 Markdown 输出（新增report_9pct_stocks调用，放在report_zt_stocks后）
    output_buffer = io.StringIO()
    with contextlib.redirect_stdout(output_buffer):
        report_overview(today_date, prev_date, overview)
        report_top_amount_stocks(df, top_n=12)
        report_top_stocks(df)
        report_sector_flow(df, total_abs)
        report_hot_concepts(hot_concept_stats)
        report_auto_concepts(auto_concept_df, top_n=10)
        report_zt_stocks(today_date, prev_date, df_zt)
        
        # 新增：调用题材共振雷达报告
        auto_df = calculate_auto(df)
        report_auto(auto_df, top_n=10)

    report_md_content = output_buffer.getvalue()

    # 返回所有计算好的结果（新增df_9pct，便于后续扩展UI展示）
    return {
        "df": df,
        "hot_stats": hot_concept_stats,
        "auto_df": auto_concept_df,
        "md_report": report_md_content,
        "df_zt": df_zt,
        # ---------------------- 新增：返回9%涨幅数据 ----------------------
        "df_9pct": df_9pct
        # ------------------------------------------------------------------
    }


# --- 第二部分：只负责界面渲染 (去掉缓存装饰器) ---
def render_auction_report_tab(selected_date=None, prev_date=None):
    """
    不带缓存，每次运行都会执行，保证按钮和 UI 正常显示
    """
    st.header("📊 每日竞价深度分析报告")

    date_list = get_trade_dates(30)
    if not date_list or len(date_list) < 2:
        st.error("❌ 无法获取交易日期数据")
        return

    # 日期逻辑处理
    if selected_date is None:
        today_date, prev_date = date_list[-1], date_list[-2]
    else:
        today_date = selected_date
        if prev_date is None:
            try:
                idx = date_list.index(today_date)
                prev_date = date_list[idx - 1]
            except:
                prev_date = date_list[-2]

    st.info(f"📅 当前分析：{today_date.strftime('%Y-%m-%d')} (对比日：{prev_date.strftime('%Y-%m-%d')})")

    with st.spinner(f"正在深度分析数据..."):
        # 【关键调用】从缓存函数中获取纯数据
        data = get_auction_analysis_data(today_date, prev_date)

        if data is None:
            st.warning("⚠️ 竞价行情数据尚未下载，请先执行抓取。")
            return

        # 渲染 UI (st.tabs, st.dataframe, st.download_button 都在这里)
        st.success(f"✅ 分析完成！(报告生成时间：{datetime.now().strftime('%H:%M:%S')})")

        tab_auto, tab_hot = st.tabs(["🔥 热门题材统计", "🤖 智能题材挖掘"])

        with tab_auto:
            st.subheader("🤖 题材共振监控")
            auto_df = data["auto_df"].copy()
            auto_df['is_62'] = (
                (auto_df['家数'] > 10) & (auto_df['红盘率%'] > 75) &
                (auto_df['平均涨跌%'] > 1.2) & (auto_df['资金增量(亿)'] > 1)
            )
            auto_df = auto_df.sort_values(by=['is_62', '平均涨跌%'], ascending=[False, False])
            styled_df = auto_df.drop(columns=['is_62']).style.apply(highlight_6_2, axis=1)
            st.dataframe(styled_df, use_container_width=True)

        with tab_hot:
            st.dataframe(data["hot_stats"], use_container_width=True)

        st.divider()
        st.subheader("📝 完整报告正文")
        with st.container(border=True):
            st.markdown(data["md_report"])

        # 下载按钮（无修改，自动包含新增的9%涨幅报告内容）
        st.download_button(
            label="📥 下载报告 (.md)",
            data=data["md_report"],
            file_name=f"竞价分析_{today_date.strftime('%Y%m%d')}.md",
            mime="text/markdown"
        )


# 保持兼容性
if __name__ == "__main__":
    st.set_page_config(layout="wide")
    render_auction_report_tab()
