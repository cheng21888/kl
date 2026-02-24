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
        ["今日竞价总额", f"{overview['total_today']:.2f} 亿", f"{m_now['sh_main_amt']:.2f} 亿", f"{m_now['cyb_amt']:.2f} 亿"],
        ["昨日竞价总额", f"{overview['total_yest']:.2f} 亿", f"{m_old['sh_main_amt']:.2f} 亿", f"{m_old['cyb_amt']:.2f} 亿"],
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
        ["竞价涨停", m_now['limit_up'], m_old['limit_up'], "竞价20cm涨停", m_now['limit_up_20cm'], m_old['limit_up_20cm']]
    ]
    
    headers = ["指标", "今日", "昨日", "指标", "今日", "昨日"]
    print(pd.DataFrame(emo_data, columns=headers).to_markdown(index=False))


def report_top_amount_stocks(df: pd.DataFrame, top_n: int = 10):
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
                   "3.1 竞价增量 Top 12", "资金流入最显著的个股")
    top_dec = df.nsmallest(10, '增量(亿)')
    print_md_table(top_dec[['股票简称', '涨跌幅', '增量(亿)', '结构标签', '热点标签']], 
                   "3.2 竞价减量 Top 12", "资金流出最显著的个股")


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
    print_md_table(stats_df[['热门概念', '个股数', '红盘率%', '平均涨跌%', '增量(亿)', '强度得分', '增量先锋', '先锋标签']].head(15),
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
    filter_cond = (
        (final_df['家数'] > 10) & 
        (final_df['红盘率%'] > 75) & 
        (final_df['平均涨跌%'] > 1.2) & 
        (final_df['资金增量(亿)'] > 1) & 
        (final_df['增量先锋'].str.contains('突发放量', na=False))
    )
    strong_concepts = final_df[filter_cond].copy()

    if strong_concepts.empty:
        print("暂无满足「家数>10、红盘率>75%、平均涨跌>1.2%、资金增量>1亿、增量先锋含突发放量」的强势题材")
    else:
        strong_concepts_sorted = strong_concepts.sort_values('资金增量(亿)', ascending=False)
        output_cols = ['题材名称', '家数', '红盘率%', '平均涨跌%', '资金增量(亿)', '状态', '增量先锋']
        print_md_table(strong_concepts_sorted[output_cols], "强势题材扩散候选池", "满足高活跃度+资金增量+突发放量的主流方向，具备题材扩散潜力")
        
        top_3_concepts = strong_concepts_sorted['题材名称'].head(3).tolist()
        print(f"\n#### 扩散方向分析：")
        print(f"1. 核心扩散主线：{', '.join(top_3_concepts) if top_3_concepts else '无'}（资金增量领先+高红盘率+放量领涨）；")
        print(f"2. 扩散逻辑：这类题材具备「资金充足+板块共识+放量突破」特征，后续可能向细分赛道/上下游题材扩散；")
        print(f"3. 关注要点：优先跟踪增量先锋中「突发放量」个股的持续性，以及题材内补涨标的机会。")
        print(f"**4. 板块强势股的低吸，前两日异动竞价个股的承接。//抑或是新题材发力抢夺资金（平量缩量市场）**")
        
        
def report_auto(final_df: pd.DataFrame, top_n: int = 10):
    """输出题材共振雷达报告"""
    if final_df.empty: return
    print("\n## 7. 🚀 题材资金共振雷达")
    display_df = final_df.head(top_n)
    cols = ['题材名称', '家数', '红盘率%', '平均涨跌%', '资金增量(亿)', '状态', '增量先锋']
    print_md_table(display_df[cols], "7.1 题材资金共振雷达 (Top 10)", "综合增量、合力程度及领涨个股性质")

    print("\n### 7.2 强势或主流方向可能的概念题材扩散方向")
    filter_cond = (
        (final_df['家数'] > 10) & 
        (final_df['红盘率%'] > 75) & 
        (final_df['平均涨跌%'] > 1.2) & 
        (final_df['资金增量(亿)'] > 1) & 
        (final_df['增量先锋'].str.contains('突发放量', na=False))
    )
    strong_concepts = final_df[filter_cond].copy()

    if strong_concepts.empty:
        print("暂无满足「家数>10、红盘率>75%、平均涨跌>1.2%、资金增量>1亿、增量先锋含突发放量」的强势题材")
    else:
        strong_concepts_sorted = strong_concepts.sort_values('资金增量(亿)', ascending=False)
        output_cols = ['题材名称', '家数', '红盘率%', '平均涨跌%', '资金增量(亿)', '状态', '增量先锋']
        print_md_table(strong_concepts_sorted[output_cols], "强势题材扩散候选池", "满足高活跃度+资金增量+突发放量的主流方向，具备题材扩散潜力")
        
        top_3_concepts = strong_concepts_sorted['题材名称'].head(3).tolist()
        print(f"\n#### 扩散方向分析：")
        print(f"1. 核心扩散主线：{', '.join(top_3_concepts) if top_3_concepts else '无'}（资金增量领先+高红盘率+放量领涨）；")
        print(f"2. 扩散逻辑：这类题材具备「资金充足+板块共识+放量突破」特征，后续可能向细分赛道/上下游题材扩散；")
        print(f"3. 关注要点：优先跟踪增量先锋中「突发放量」个股的持续性，以及题材内补涨标的机会。")
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
    
    
def report_zf_stocks(today_date: datetime, prev_date: datetime, df_9pct: pd.DataFrame) -> None:
    """ 输出竞价涨幅＞9%个股分析报告（适配最新数据结构） """
    print(f"\n# 📈 竞价涨幅＞9%个股分析 ({today_date.strftime('%Y-%m-%d')})")

    if df_9pct.empty:
        print("\n**无数据**")
        return

    # 1. 识别涨幅字段（兼容多种命名）
    pct_col = None
    for col in ['涨跌幅', '涨跌幅_今', '竞价涨跌幅%']:
        if col in df_9pct.columns:
            pct_col = col
            break
    
    # 识别竞价金额字段
    amt_col = None
    for col in ['竞价金额', '竞价金额_今']:
        if col in df_9pct.columns:
            amt_col = col
            break

    # 2. 核心统计汇总
    p9_count = len(df_9pct)
    cm20_count = 0
    if pct_col:
        cm20_count = len(df_9pct[df_9pct[pct_col] > 19])

    print(f"\n**今日竞价涨幅＞9%总数**: {p9_count} 只 (其中 20CM: {cm20_count} 只)")

    # 3. 连板与超跌统计（新增）
    if '筛选条件' in df_9pct.columns:
        lb_count = len(df_9pct[df_9pct['筛选条件'] == '连板加速'])
        cd_count = len(df_9pct[df_9pct['筛选条件'] == '超跌反弹'])
        print(f"**条件筛选**: 连板加速 {lb_count} 只 | 超跌反弹 {cd_count} 只")

    # 4. 竞价金额统计
    if amt_col:
        avg_amt = (df_9pct[amt_col].mean() / 1e8).round(4)
        max_amt = (df_9pct[amt_col].max() / 1e8).round(4)
        total_amt = (df_9pct[amt_col].sum() / 1e8).round(4)
        print(f"**竞价金额统计**: 总额 {total_amt} 亿 | 平均 {avg_amt} 亿 | 最高 {max_amt} 亿")

    # 5. 详情表处理
    df_display = df_9pct.copy()
    
    # 按竞价金额降序排序
    if amt_col:
        df_display = df_display.sort_values(amt_col, ascending=False)
        df_display['竞价金额(亿)'] = (df_display[amt_col] / 1e8).round(4)
    
    # 定义展示列（按重要性排序）
    base_cols = ['股票简称']
    
    # 涨幅列
    if pct_col:
        df_display = df_display.rename(columns={pct_col: '涨幅%'})
        base_cols.append('涨幅%')
    
    # 金额相关
    base_cols.extend(['竞价金额(亿)'])
    if '增量(亿)' in df_display.columns:
        base_cols.append('增量(亿)')
    if '竞价放量倍数' in df_display.columns:
        df_display['放量倍数'] = df_display['竞价放量倍数'].round(2)
        base_cols.append('放量倍数')
    
    # 连板相关
    if '连续涨停天数' in df_display.columns:
        df_display['连板'] = df_display['连续涨停天数'].astype(int)
        base_cols.append('连板')
    
    # 条件筛选
    if '筛选条件' in df_display.columns:
        base_cols.append('筛选条件')
    
    # 昨日涨跌幅（用于超跌分析）
    if '涨跌幅_昨收' in df_display.columns:
        df_display['昨收%'] = df_display['涨跌幅_昨收'].round(2)
        base_cols.append('昨收%')
    
    # 基础信息
    info_cols = ['所属行业', '流通市值(亿)', '结构标签', '热点标签', '热点关键词']
    for col in info_cols:
        if col in df_display.columns:
            base_cols.append(col)
    
    # 封单信息（如果有）
    if '封单额(亿)' in df_display.columns:
        df_display['封单(亿)'] = df_display['封单额(亿)'].round(4)
        base_cols.append('封单(亿)')
    
    # 历史涨停原因
    if '历史涨停原因类别' in df_display.columns:
        base_cols.append('历史涨停原因类别')
    
    # 过滤存在的列
    final_show = [c for c in base_cols if c in df_display.columns]
    
    # 6. 输出详情表格
    print("\n**📊 详细列表（按竞价金额降序）**")
    if not df_display[final_show].empty:
        # 格式化数值列
        for col in final_show:
            if col in ['涨幅%', '昨收%'] and col in df_display.columns:
                df_display[col] = df_display[col].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "--")
        
        print(pd.DataFrame(df_display[final_show]).to_markdown(index=False))
    else:
        print("无数据显示")

    # 7. 添加简要分析结论
    print(f"\n**💡 简要点评**")
    insights = []
    
    # 根据筛选条件分析
    if '筛选条件' in df_display.columns:
        lb_df = df_display[df_display['筛选条件'] == '连板加速']
        if not lb_df.empty and amt_col:
            top_lb = lb_df.iloc[0]['股票简称'] if '股票简称' in lb_df.columns else ""
            insights.append(f"连板加速龙头: {top_lb}")
        
        cd_df = df_display[df_display['筛选条件'] == '超跌反弹']
        if not cd_df.empty and amt_col:
            top_cd = cd_df.iloc[0]['股票简称'] if '股票简称' in cd_df.columns else ""
            insights.append(f"超跌反弹先锋: {top_cd}")
    
    # 热点分布
    if '热点标签' in df_display.columns or '热点关键词' in df_display.columns:
        hot_col = '热点标签' if '热点标签' in df_display.columns else '热点关键词'
        all_hot = []
        for _, row in df_display.head(10).iterrows():
            if pd.notna(row.get(hot_col)) and row[hot_col]:
                all_hot.extend([h.strip() for h in str(row[hot_col]).split(',') if h.strip()])
        if all_hot:
            from collections import Counter
            top_hot = Counter(all_hot).most_common(3)
            hot_str = "、".join([f"{h[0]}({h[1]}只)" for h in top_hot])
            insights.append(f"热点聚焦: {hot_str}")
    
    if insights:
        for insight in insights:
            print(f"- {insight}")
    else:
        print("- 无明显集中特征")
