import streamlit as st
import io
import contextlib
import pandas as pd
from datetime import datetime
from collections import Counter, defaultdict
import re
from mod.config import SAVE_DIR
from mod.data_loader import get_trade_dates
from mod.analyzer import (
    analyze_auction_flow, calculate_hot_concepts, calculate_auto_concepts, build_zt_tags, build_zf_tags
)
from mod.reporter import (
    report_overview, report_top_stocks, report_sector_flow, report_top_amount_stocks,
    report_hot_concepts, report_auto_concepts, report_zt_stocks, report_zf_stocks
)


# ---------------------- 修改：单个表格的行业关键词分析函数 ----------------------
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


def report_9p(today_date: datetime, prev_date: datetime, df_9pct: pd.DataFrame) -> pd.DataFrame:
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


# ---------------------- 新增：竞价强势股分析函数 ----------------------
def analyze_zf_stocks(today_date: datetime, prev_date: datetime) -> pd.DataFrame:
    """
    分析竞价强势股（连板天数≥2，竞价放量≥1倍，今日涨幅>昨日涨幅）
    
    Args:
        today_date: 当前日期
        prev_date: 前一个交易日
    
    Returns:
        DataFrame: 符合条件的强势股数据
    """
    print(f"\n{'='*60}")
    print(f"🏆 竞价强势股分析 (连板≥2 | 放量≥1倍 | 涨幅递增)")
    print(f"{'='*60}")
    
    # 调用build_zf_tags函数构建数据
    df_zf = build_zf_tags(today_date, prev_date)
    
    if df_zf.empty:
        print("\n**没有符合条件的股票**")
        return pd.DataFrame()
    
    # 调用report_zf_stocks函数输出报告
    report_zf_stocks(today_date, prev_date, df_zf)
    
    # 对本表格进行关键词分析
    analyze_single_table_keywords(df_zf, "竞价强势股", top_n=5)
    
    return df_zf


# ---------------------- 主程序入口（用于测试） ----------------------
if __name__ == "__main__":
    # 测试代码
    from datetime import datetime, timedelta
    
    # 设置测试日期
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    prev = today - timedelta(days=1)
    
    # 运行强势股分析
    df_result = analyze_zf_stocks(today, prev)
    
    if not df_result.empty:
        print(f"\n✅ 分析完成，共 {len(df_result)} 只股票符合条件")
        print("\n数据预览：")
        print(df_result.head())
