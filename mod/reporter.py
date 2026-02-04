import pandas as pd
from datetime import datetime
from .utils import print_md_table


def report_overview(today_date: datetime, prev_date: datetime, overview: dict):
    """输出市场概览报告 (定制增强版)"""
    print(f"# 📊 A股竞价资金流向监控报告 ({today_date.strftime('%Y-%m-%d')})")
    print(f"\n> 对比交易日：{prev_date.strftime('%Y-%m-%d')} | 数据来源：本地行情导出")

    m_now = overview['metrics_now']
    m_old = overview['metrics_old']

    # 1. 核心资金面
    print("\n## 1. 核心资金面")
    data = [
        ["今日竞价总额", f"{overview['total_today']:.2f} 亿", f"{m_now['sh_main_amt']:.2f} 亿",
         f"{m_now['cyb_amt']:.2f} 亿"],
        ["昨日竞价总额", f"{overview['total_yest']:.2f} 亿", f"{m_old['sh_main_amt']:.2f} 亿",
         f"{m_old['cyb_amt']:.2f} 亿"],
        ["资金净增减", f"{overview['net_change']:+.2f} 亿 ({overview['ratio']:.2%})",
         f"{m_now['sh_main_amt'] - m_old['sh_main_amt']:+.2f} 亿",
         f"{m_now['cyb_amt'] - m_old['cyb_amt']:+.2f} 亿"]
    ]
    print(pd.DataFrame(data, columns=["指标", "全市场", "上海市场", "创业板"]).to_markdown(index=False))

    # 2. 市场情绪指标 (左右并排布局)
    print("\n## 2. 市场情绪指标")

    # 计算涨跌比 (上涨家数 : 下跌家数)
    ratio_now = f"{(m_now['up_count'] / (m_now['down_count'] or 1)):.2f}"
    ratio_old = f"{(m_old['up_count'] / (m_old['down_count'] or 1)):.2f}"

    emo_data = [
        ["竞价强力(>7%)", m_now['strong'], m_old['strong'], "竞价涨跌比", ratio_now, ratio_old],
        ["竞价极弱(<-7%)", m_now['weak'], m_old['weak'], "竞价跌停", m_now['limit_down'], m_old['limit_down']],
        ["竞价涨停", m_now['limit_up'], m_old['limit_up'], "竞价20cm涨停", m_now['limit_up_20cm'],
         m_old['limit_up_20cm']]
    ]

    headers = ["指标", "今日", "昨日", "指标", "今日", "昨日"]
    print(pd.DataFrame(emo_data, columns=headers).to_markdown(index=False))


def report_top_amount_stocks(df: pd.DataFrame, top_n: int = 12):
    """输出成交额前N名的个股报告"""
    print(f"\n## 7. 竞价成交额 Top {top_n}")
    top_amt = df.nlargest(top_n, '竞价金额_今').copy()
    top_amt['竞价金额(亿)'] = (top_amt['竞价金额_今'] / 1e8).round(4)
    cols = ['股票简称', '涨跌幅', '竞价金额(亿)', '增量(亿)', '结构标签', '热点标签']
    print_md_table(top_amt[cols], f"7.1 竞价成交额前 {top_n} 名", "全市场竞价吸金最强的个股")


def report_top_stocks(df: pd.DataFrame):
    """输出个股异动报告"""
    print("\n## 3. 个股竞价异动穿透")
    top_inc = df.nlargest(10, '增量(亿)')
    print_md_table(top_inc[['股票简称', '涨跌幅', '增量(亿)', '结构标签', '热点标签']],
                   "3.1 竞价增量 Top 10", "资金流入最显著的个股")
    top_dec = df.nsmallest(10, '增量(亿)')
    print_md_table(top_dec[['股票简称', '涨跌幅', '增量(亿)', '结构标签', '热点标签']],
                   "3.2 竞价减量 Top 10", "资金流出最显著的个股")


def report_sector_flow(df: pd.DataFrame, total_abs: float):
    """输出行业流向报告"""
    if '所属行业' not in df.columns: return
    print("\n## 4. 行业资金分布")
    sector_grp = df.groupby('所属行业').agg(
        增量_亿=('增量(亿)', 'sum'),
        平均涨幅=('涨跌幅', 'mean'),
        家数=('股票代码', 'count')
    ).reset_index()
    sector_grp['占比%'] = (sector_grp['增量_亿'].abs() / total_abs * 100).round(2)
    top_sectors = sector_grp.sort_values('增量_亿', ascending=False).head(10)
    print_md_table(top_sectors, "4.1 行业增量榜", "资金流入前十行业")


def report_hot_concepts(stats: list):
    """输出热门概念报告"""
    if not stats: return
    print("\n## 5. 重点题材穿透")
    stats_df = pd.DataFrame(stats).sort_values('强度得分', ascending=False)
    print_md_table(
        stats_df[['热门概念', '个股数', '红盘率%', '平均涨跌%', '增量(亿)', '强度得分', '增量先锋', '先锋标签']].head(
            15),
        "5.1 热门题材动能监控", "核心动能榜")
    print_md_table(stats_df[['热门概念', '关键异动']].head(20),
                   "5.2 题材异动个股穿透", "板块内部活跃结构明细")


def report_auto_concepts(final_df: pd.DataFrame, top_n: int = 10):
    """输出题材共振雷达报告"""
    if final_df.empty: return
    print("\n## 6. 🚀 题材资金共振雷达")
    display_df = final_df.head(top_n)
    cols = ['题材名称', '家数', '红盘率%', '平均涨跌%', '资金增量(亿)', '状态', '增量先锋']
    print_md_table(display_df[cols], "6.1 题材资金共振雷达 (Top 10)", "综合增量、合力程度及领涨个股性质")

    print("\n### 6.2 强势或主流方向可能的概念题材扩散方向")

    # 修改筛选条件：增加对昨日首板的判断
    filter_cond = (
            (final_df['家数'] > 10) &
            (final_df['红盘率%'] > 75) &
            (final_df['平均涨跌%'] > 0.8) &
            (final_df['资金增量(亿)'] > 1) &
            (
                    final_df['增量先锋'].str.contains('突发放量', na=False) |
                    (
                            final_df['增量先锋'].str.contains('昨日首板', na=False) &
                            final_df['增量先锋'].apply(lambda x:
                                                       any('[昨日首板]' in str(item) and
                                                           '(' in str(item) and '%)' in str(item) and
                                                           float(str(item).split('(')[1].split('%')[0]) > 9.8
                                                           for item in str(x).split(', ') if '[昨日首板]' in str(item))
                                                       if pd.notnull(x) else False
                                                       )
                    ) |
                    (
                            final_df['增量先锋'].str.contains('昨日跌停', na=False) &
                            final_df['增量先锋'].apply(lambda x:
                                                       any('[昨日跌停]' in str(item) and
                                                           '(' in str(item) and '%)' in str(item) and
                                                           float(str(item).split('(')[1].split('%')[0]) > -7
                                                           for item in str(x).split(', ') if '[昨日跌停]' in str(item))
                                                       if pd.notnull(x) else False
                                                       )
                    ) |
                    (

                        (final_df['红盘率%'] > 80) &
                        (final_df['平均涨跌%'] > 1.5) &
                        (final_df['资金增量(亿)'] > 2) &
                            final_df['增量先锋'].str.contains('昨日首板', na=False) &
                            final_df['增量先锋'].apply(lambda x:
                                                       any('[昨日首板]' in str(item) and
                                                           '(' in str(item) and '%)' in str(item) and
                                                           float(str(item).split('(')[1].split('%')[0]) > 4
                                                           for item in str(x).split(', ') if '[昨日首板]' in str(item))
                                                       if pd.notnull(x) else False
                                                       )
                    )
            )
    )

    strong_concepts = final_df[filter_cond].copy()

    if strong_concepts.empty:
        print("暂无满足「家数>10、红盘率>75%、平均涨跌>1.2%、资金增量>1亿、增量先锋含突发放量或昨日首板」的强势题材")
    else:
        strong_concepts_sorted = strong_concepts.sort_values('资金增量(亿)', ascending=False)
        output_cols = ['题材名称', '家数', '红盘率%', '平均涨跌%', '资金增量(亿)', '状态', '增量先锋']
        print_md_table(strong_concepts_sorted[output_cols], "强势题材扩散候选池",
                       "满足高活跃度+资金增量+突发放量/昨日首板的强势方向，具备题材扩散潜力")

        top_3_concepts = strong_concepts_sorted['题材名称'].head(3).tolist()

        # 提取增量先锋中的关键信息用于分析
        def extract_pioneer_info(series):
            info = []
            for val in series:
                if isinstance(val, str):
                    if '突发放量' in val:
                        info.append('突发放量')
                    if '昨日首板' in val:
                        info.append('昨日首板')
            return list(set(info))  # 去重

        if not strong_concepts_sorted.empty:
            pioneer_types = extract_pioneer_info(strong_concepts_sorted['增量先锋'])
        else:
            pioneer_types = []

        print(f"\n#### 扩散方向分析：")
        print(
            f"1. 核心扩散主线：{', '.join(top_3_concepts) if top_3_concepts else '无'}（资金增量领先+高红盘率+{'/'.join(pioneer_types)}）；")
        print(
            f"2. 扩散逻辑：这类题材具备「资金充足+板块共识+{'/'.join(pioneer_types)}」特征，后续可能向细分赛道/上下游题材扩散；")
        print(f"3. 关注要点：优先跟踪增量先锋中「{'/'.join(pioneer_types)}」个股的持续性，以及题材内补涨标的机会。")
        print(f"**4. 板块强势股的低吸，前两日异动竞价个股的承接。//抑或是新题材发力抢夺资金（平量缩量市场）**")


def report_zt_stocks(today_date: datetime, prev_date: datetime, df_zt: pd.DataFrame) -> None:
    """ 输出报告 """
    print(f"\n# 🎯 竞价涨停/强单分析 ({today_date.strftime('%Y-%m-%d')})")

    # 1. 统计
    zt_count = len(df_zt)
    cm20_count = len(df_zt[df_zt['涨跌幅'] > 19]) if '涨跌幅' in df_zt.columns else 0

    print(f"\n**今日竞价封死总数**: {zt_count} 只 (其中 20CM: {cm20_count} 只)")

    if '封单额(亿)' in df_zt.columns:
        pos = len(df_zt[df_zt['封单额(亿)'] > 0])
        neg = len(df_zt[df_zt['封单额(亿)'] < 0])
        print(f"**封单分布**: 买盘净封死 {pos} 只 | 卖盘强压 {neg} 只")

    # 2. 详情表
    df_display = df_zt.copy()
    if '封单额(亿)' in df_display.columns:
        df_display = df_display.sort_values('封单额(亿)', ascending=False)
        df_display['封单(亿)'] = df_display['封单额(亿)'].map(lambda x: f"{x:.2f}")

    show_cols = ['股票简称', '涨跌幅', '封单(亿)', '所属行业', '流通市值(亿)', '历史涨停原因类别']
    final_show = [c for c in show_cols if c in df_display.columns]

    print_md_table(df_display[final_show], "竞价涨停列表 (按封单额降序)")


def report_9pct_stocks(today_date: datetime, prev_date: datetime, df_9pct: pd.DataFrame) -> None:
    """ 输出竞价涨幅＞9%个股分析报告（使用竞价金额排序，无封单额时） """
    print(f"\n# 📈 竞价涨幅＞9%个股分析 ({today_date.strftime('%Y-%m-%d')})")

    # 1. 核心统计汇总
    p9_count = len(df_9pct)
    cm20_count = len(df_9pct[df_9pct['涨跌幅'] > 19]) if '涨跌幅' in df_9pct.columns else 0

    print(f"\n**今日竞价涨幅＞9%总数**: {p9_count} 只 (其中 20CM: {cm20_count} 只)")

    # 2. 竞价金额分布（若存在该字段）
    if '竞价金额_今' in df_9pct.columns:
        avg_amount = df_9pct['竞价金额_今'].mean()
        max_amount = df_9pct['竞价金额_今'].max()
        print(f"**竞价金额统计**: 平均 {avg_amount:.2f} 亿 | 最高 {max_amount:.2f} 亿")

    # 3. 详情表（按竞价金额降序排序）
    df_display = df_9pct.copy()
    if '竞价金额_今' in df_display.columns:
        df_display = df_display.sort_values('竞价金额_今', ascending=False)
        df_display['竞价金额(亿)'] = (df_display['竞价金额_今'] / 1e8).round(4)

    # 定义展示列（自动过滤不存在的列）
    show_cols = ['股票简称', '涨跌幅', '竞价金额(亿)', '所属行业', '流通市值(亿)', '结构标签', '热点标签']
    final_show = [c for c in show_cols if c in df_display.columns]

    # 输出markdown表格
    print_md_table(df_display[final_show], "竞价涨幅＞9%列表 (按竞价金额降序)")