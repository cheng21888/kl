import streamlit as st
import io
import contextlib
import pandas as pd
from datetime import datetime
from collections import Counter, defaultdict
import re
import numpy as np
from modules.config import SAVE_DIR
from modules.data_loader import get_trade_dates, read_market_data
from modules.analyzer import (
    analyze_auction_flow, calculate_hot_concepts, calculate_auto_concepts, build_zt_tags
)
from modules.reporter import (
    report_overview, report_top_stocks, report_sector_flow, report_top_amount_stocks,
    report_hot_concepts, report_auto_concepts, report_zt_stocks
)


# ---------------------- 单个表格的行业关键词分析函数 ----------------------
def analyze_single_table_keywords(df: pd.DataFrame, table_name: str, top_n: int = 5) -> None:
    """
    分析单个表格的行业关键词（改进版：相同关键词在一个格子中只统计一次）

    Args:
        df: 包含'所属行业'列的DataFrame
        table_name: 表格名称（用于显示）
        top_n: 返回前N个关键词
    """
    if df is None or df.empty or '所属行业' not in df.columns:
        print(f"⚠️ {table_name}: 无有效数据或缺少'所属行业'列")
        return

    keyword_counter = Counter()  # 关键词计数器
    keyword_to_sectors = defaultdict(set)  # 用于存储词语对应的完整板块

    # 提取"所属行业"列
    industries = df['所属行业'].dropna().tolist()

    # 处理每个行业的文本
    for industry in industries:
        if not isinstance(industry, str):
            continue

        # 分割成完整的板块名称（如：食品饮料、白酒、白酒Ⅲ）
        sectors = re.split(r'[-]', industry)

        # 用于记录当前格子中已出现的关键词（避免重复计数）
        keywords_in_current_cell = set()

        for sector in sectors:
            sector = sector.strip()
            if not sector:
                continue

            # 从板块名称中提取2个字的词语
            for i in range(len(sector) - 1):
                word = sector[i:i + 2]
                # 检查是否是中文字符（排除数字、字母、特殊符号）
                if all('\u4e00' <= char <= '\u9fff' for char in word):
                    keywords_in_current_cell.add(word)
                    keyword_to_sectors[word].add(sector)

        # 将当前格子中的所有唯一关键词计数（每个关键词最多+1）
        for keyword in keywords_in_current_cell:
            keyword_counter[keyword] += 1

    # 检查是否有有效关键词
    if not keyword_counter:
        print(f"📊 {table_name}行业关键词分析: 未找到有效的行业关键词")
        return

    # 获取前top_n个关键词
    top_keywords = keyword_counter.most_common(top_n)

    # 输出结果
    print(f"\n📊 {table_name}行业关键词分析")
    print(f"**涉及股票数量**: {len(df)} 只")
    print(f"**唯一2字词语数**: {len(keyword_counter)} 个")
    print(f"**前{top_n}个高频词语**:")
    print("| 词语(出现股票数) | 对应完整板块 |")
    print("|-----------------|-------------|")

    for keyword, count in top_keywords:
        # 获取该词语对应的所有完整板块
        sectors = list(keyword_to_sectors[keyword])
        sectors_str = ", ".join(sorted(sectors))
        print(f"| {keyword}({count}) | {sectors_str} |")


# ---------------------- 竞价涨幅＞9%分析函数 ----------------------
def report_9pct_stocks(today_date: datetime, prev_date: datetime, df_9pct: pd.DataFrame) -> pd.DataFrame:
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

    # 4. 在表格下方单独分析本表格的关键词
    analyze_single_table_keywords(df_9pct, "竞价涨幅＞9%", top_n=5)

    return df_9pct  # 返回数据


# ---------------------- 竞价涨幅＞7%分析函数 ----------------------
def report_7pct_stocks(today_date: datetime, prev_date: datetime, df_7pct: pd.DataFrame) -> pd.DataFrame:
    """ 输出竞价涨幅＞7%个股分析报告（适配无封单额、按竞价金额排序，与9%逻辑完全对齐） """
    print(f"\n# 📊 竞价涨幅＞7%个股分析 ({today_date.strftime('%Y-%m-%d')})")

    # 1. 核心统计汇总（同9%格式，区分20CM）
    p7_count = len(df_7pct)
    cm20_count = len(df_7pct[df_7pct['涨跌幅'] > 19]) if '涨跌幅' in df_7pct.columns else 0

    print(f"\n**今日竞价涨幅＞7%总数**: {p7_count} 只 (其中 20CM: {cm20_count} 只)")

    # 2. 竞价金额统计（与9%、report_top_amount_stocks保持单位/精度一致）
    if '竞价金额_今' in df_7pct.columns:
        avg_amt = (df_7pct['竞价金额_今'].mean() / 1e8).round(4)
        max_amt = (df_7pct['竞价金额_今'].max() / 1e8).round(4)
        print(f"**竞价金额统计**: 平均 {avg_amt} 亿 | 最高 {max_amt} 亿")

    # 3. 详情表处理（按竞价金额降序，单位转换+保留4位小数，同9%逻辑）
    df_display = df_7pct.copy()
    if '竞价金额_今' in df_display.columns:
        df_display = df_display.sort_values('竞价金额_今', ascending=False)
        df_display['竞价金额(亿)'] = (df_display['竞价金额_今'] / 1e8).round(4)

    # 定义展示列（与9%完全一致，自动过滤不存在的列，兼容数据结构）
    show_cols = ['股票简称', '涨跌幅', '竞价金额(亿)', '增量(亿)', '所属行业', '流通市值(亿)', '结构标签', '热点标签']
    final_show = [c for c in show_cols if c in df_display.columns]

    # 输出markdown表格（复用现有工具，与9%、涨停报告格式统一）
    print(pd.DataFrame(df_display[final_show]).to_markdown(index=False))

    # 4. 在表格下方单独分析本表格的关键词
    analyze_single_table_keywords(df_7pct, "竞价涨幅＞7%", top_n=5)

    return df_7pct  # 返回数据


# ---------------------- 新增：特殊条件筛选分析函数 ----------------------
# ---------------------- 修复后的特殊条件筛选分析函数 ----------------------
def report_special_conditions(today_date: datetime, prev_date: datetime, df: pd.DataFrame) -> pd.DataFrame:
    """
    筛选满足特定条件的股票并生成表格
    条件：
    1. 连续涨停天数 >= 2，竞价放量倍数 >= 1，今日竞价涨幅 > 昨日收盘涨跌幅
    2. 或者：昨日收盘涨跌幅在 -9.8% 到 -5% 之间，且今日竞价成交额 > 昨日竞价成交额
    """
    print(f"\n# 🎯 特殊条件筛选分析 ({today_date.strftime('%Y-%m-%d')})")
    
    if df is None or df.empty:
        print("⚠️ 无有效数据")
        return pd.DataFrame()
    
    # 获取昨日收盘数据
    df_close = read_market_data(prev_date, '收盘行情')
    df_yest_auction = read_market_data(prev_date, '竞价行情')
    df_limit = read_market_data(prev_date, '收盘涨跌停')

    
    if df_close.empty or df_yest_auction.empty or df_limit.empty:
        print("⚠️ 无法获取昨日收盘数据或昨日竞价数据")
        return pd.DataFrame()
    
    # 准备数据
    df_analysis = df.copy()
    
    # 合并昨日收盘数据（涨跌幅）
    df_analysis = df_analysis.merge(
        df_close[['股票代码', '涨跌幅']].rename(columns={'涨跌幅': '昨日收盘涨跌幅'}),
        on='股票代码',
        how='left'
    )
    
    # 合并昨日竞价数据（用于成交额对比）
    df_analysis = df_analysis.merge(
        df_yest_auction[['股票代码', '竞价金额']].rename(columns={'竞价金额': '昨日竞价成交额'}),
        on='股票代码',
        how='left'
    )
    
    # ========== 关键修复：合并涨停数据 ==========
    # 从收盘涨跌停表中合并连续涨停天数
    df_analysis = df_analysis.merge(
        df_limit[['股票代码', '连续涨停天数']],  # 直接使用正确的列名
        on='股票代码',
        how='left'
    )
    # ========== 修复结束 ==========
    
    # 填充缺失值前确保列存在
    required_cols = {
        '昨日收盘涨跌幅': 0,
        '昨日竞价成交额': 1e6,
        '连续涨停天数': 0,
        '竞价金额_今': 0,
        '涨跌幅': 0,
    }
    
    for col, default_val in required_cols.items():
        if col in df_analysis.columns:
            df_analysis[col] = pd.to_numeric(df_analysis[col], errors='coerce').fillna(default_val)
        else:
            df_analysis[col] = default_val
    
    df_analysis['连续涨停天数'] = df_analysis['连续涨停天数'].astype(int)
    
    # 条件1：连板股放量高开（连续涨停天数 >= 2）
    cond1 = (
        (df_analysis['连续涨停天数'] >= 2) &
        (df_analysis['竞价金额_今'] > df_analysis['昨日竞价成交额']) &
        (df_analysis['涨跌幅'] > df_analysis['昨日收盘涨跌幅'])
    )
    
    # 条件2：大跌后竞价放量（昨日收盘涨跌幅在-9.8%到-5%之间）
    cond2 = (
        (df_analysis['昨日收盘涨跌幅'] > -9.8) &
        (df_analysis['昨日收盘涨跌幅'] < -5) &
        (df_analysis['竞价金额_今'] > df_analysis['昨日竞价成交额'])
    )
    
    # 合并两个条件
    df_filtered = df_analysis[cond1 | cond2].copy()
    
    if df_filtered.empty:
        print("⚠️ 没有股票满足筛选条件")
        return pd.DataFrame()
    
    # 统计信息
    total_count = len(df_filtered)
    cond1_count = len(df_analysis[cond1])
    cond2_count = len(df_analysis[cond2])
    
    print(f"\n**满足条件总数**: {total_count} 只")
    print(f"- 条件1(连板放量高开): {cond1_count} 只")
    print(f"- 条件2(大跌后竞价放量): {cond2_count} 只")
    
    # 竞价金额统计
    if '竞价金额_今' in df_filtered.columns:
        avg_amt = (df_filtered['竞价金额_今'].mean() / 1e8).round(4)
        max_amt = (df_filtered['竞价金额_今'].max() / 1e8).round(4)
        print(f"\n**竞价金额统计**: 平均 {avg_amt} 亿 | 最高 {max_amt} 亿")
    
    # 按条件分类并排序
    df_filtered['筛选条件'] = '其他'
    df_filtered.loc[cond1[df_filtered.index], '筛选条件'] = '连板放量高开'
    df_filtered.loc[cond2[df_filtered.index], '筛选条件'] = '大跌后竞价放量'
    
    # 按竞价金额降序排序
    df_filtered = df_filtered.sort_values('竞价金额_今', ascending=False)
    
    # 准备展示数据
    df_display = df_filtered.copy()
    
    # 转换金额单位为亿
    if '竞价金额_今' in df_display.columns:
        df_display['竞价金额(亿)'] = (df_display['竞价金额_今'] / 1e8).round(4)
    
    if '昨日竞价成交额' in df_display.columns:
        df_display['昨日竞价(亿)'] = (df_display['昨日竞价成交额'] / 1e8).round(4)
    
    # 格式化涨跌幅显示
    df_display['涨跌幅%'] = df_display['涨跌幅'].round(2)
    df_display['昨日收盘%'] = df_display['昨日收盘涨跌幅'].round(2)
    
    # 定义展示列
    show_cols = [
        '股票简称', '筛选条件', '涨跌幅%', '昨日收盘%', 
        '竞价金额(亿)', '昨日竞价(亿)', '所属行业', '流通市值(亿)', 
        '结构标签', '热点标签', '连续涨停天数'  # 可以加上这一列用于验证
    ]
    final_show = [c for c in show_cols if c in df_display.columns]
    
    # 输出markdown表格
    print("\n### 📋 筛选结果详情")
    if final_show:
        print(pd.DataFrame(df_display[final_show]).to_markdown(index=False))
    else:
        print("⚠️ 没有可显示的列")
    
    # 按条件分组统计
    if '筛选条件' in df_filtered.columns and len(df_filtered['筛选条件'].unique()) > 0:
        print("\n### 📊 按条件分组统计")
        group_stats = df_filtered.groupby('筛选条件').agg({
            '股票代码': 'count',
            '竞价金额_今': lambda x: (x.sum() / 1e8).round(2) if x.sum() > 0 else 0,
            '涨跌幅': 'mean'
        }).round(2)
        group_stats.columns = ['股票数量', '总竞价金额(亿)', '平均涨幅%']
        print(group_stats.to_markdown())
    
    # 分析行业关键词
    analyze_single_table_keywords(df_filtered, "特殊条件筛选", top_n=5)
    
    return df_filtered


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

    # 筛选竞价涨幅＞9%个股数据
    df_9pct = df[df['涨跌幅'] > 9].copy()
    # 筛选竞价涨幅＞7%个股数据
    df_7pct = df[df['涨跌幅'] > 7].copy()

    # 2. 计算其他题材数据
    total_abs = df['增量(亿)'].abs().sum()
    hot_concept_stats = calculate_hot_concepts(df)
    auto_concept_df = calculate_auto_concepts(df)

    # 3. 捕获 Markdown 输出
    output_buffer = io.StringIO()
    with contextlib.redirect_stdout(output_buffer):
        report_overview(today_date, prev_date, overview)
        # 调用报告函数（内部已包含关键词分析）
        df_7pct_data = report_7pct_stocks(today_date, prev_date, df_7pct)
        df_9pct_data = report_9pct_stocks(today_date, prev_date, df_9pct)
        # 新增：特殊条件筛选分析
        df_special = report_special_conditions(today_date, prev_date, df)

    report_md_content = output_buffer.getvalue()

    # 返回所有计算好的结果
    return {
        "df": df,
        "hot_stats": hot_concept_stats,
        "auto_df": auto_concept_df,
        "md_report": report_md_content,
        "df_zt": df_zt,
        "df_9pct": df_9pct,
        "df_7pct": df_7pct,
        "df_special": df_special  # 新增
    }


# --- 第二部分：只负责界面渲染 (去掉缓存装饰器) ---
def bankuai_tab(selected_date=None, prev_date=None):
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

        # 渲染 UI
        st.success(f"✅ 分析完成！(报告生成时间：{datetime.now().strftime('%H:%M:%S')})")

        # 创建三个标签页
        tab_auto, tab_hot, tab_special = st.tabs(["🔥 热门题材统计", "🤖 智能题材挖掘", "🎯 特殊条件筛选"])

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
            st.subheader("🔥 热门题材统计")
            st.dataframe(data["hot_stats"], use_container_width=True)

        with tab_special:
            st.subheader("🎯 特殊条件筛选结果")
            if "df_special" in data and data["df_special"] is not None and not data["df_special"].empty:
                df_special_display = data["df_special"].copy()
                
                # 准备展示数据
                if '竞价金额_今' in df_special_display.columns:
                    df_special_display['竞价金额(亿)'] = (df_special_display['竞价金额_今'] / 1e8).round(4)
                
                if '昨日竞价成交额' in df_special_display.columns:
                    df_special_display['昨日竞价(亿)'] = (df_special_display['昨日竞价成交额'] / 1e8).round(4)
                
                # 格式化涨跌幅
                if '涨跌幅' in df_special_display.columns:
                    df_special_display['涨跌幅%'] = df_special_display['涨跌幅'].round(2)
                
                if '昨日收盘涨跌幅' in df_special_display.columns:
                    df_special_display['昨日收盘%'] = df_special_display['昨日收盘涨跌幅'].round(2)
                
                # 选择要显示的列
                display_cols = [
                    '股票简称', '筛选条件', '涨跌幅%', '昨日收盘%',
                    '竞价金额(亿)', '昨日竞价(亿)', '所属行业', '结构标签'
                ]
                display_cols = [c for c in display_cols if c in df_special_display.columns]
                
                st.dataframe(df_special_display[display_cols], use_container_width=True)
                
                # 显示统计信息
                st.subheader("📊 统计摘要")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("满足条件总数", len(df_special_display))
                with col2:
                    cond1_count = len(df_special_display[df_special_display['筛选条件'] == '连板放量高开'])
                    st.metric("连板放量高开", cond1_count)
                with col3:
                    cond2_count = len(df_special_display[df_special_display['筛选条件'] == '大跌后竞价放量'])
                    st.metric("大跌后竞价放量", cond2_count)
                
                # 分组统计
                if '筛选条件' in df_special_display.columns:
                    st.subheader("📈 分组统计")
                    group_stats = df_special_display.groupby('筛选条件').agg({
                        '股票简称': 'count',
                        '竞价金额(亿)': 'sum',
                        '涨跌幅%': 'mean'
                    }).round(2)
                    group_stats.columns = ['股票数量', '总竞价金额(亿)', '平均涨幅%']
                    st.dataframe(group_stats, use_container_width=True)
            else:
                st.info("ℹ️ 没有股票满足筛选条件")

        st.divider()
        st.subheader("📝 完整报告正文")
        with st.container(border=True):
            st.markdown(data["md_report"])

        # 下载按钮
        st.download_button(
            label="📥 下载报告 (.md)",
            data=data["md_report"],
            file_name=f"竞价分析_{today_date.strftime('%Y%m%d')}.md",
            mime="text/markdown"
        )


# 保持兼容性
if __name__ == "__main__":
    st.set_page_config(layout="wide")
    bankuai_tab()
