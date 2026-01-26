import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List
from .data_loader import read_market_data, load_concept_data
from .utils import clean_dataframe,standardize_code
from .config import HOT_KEYWORDS, BLACKLIST, HOT_CONCEPT_LIST
import streamlit as st
@st.cache_data
def build_structure_tags(today_date: datetime, prev_date: datetime) -> pd.DataFrame:
    """构建昨日形态 + 今日竞价放量 → 结构标签"""
    df_today = read_market_data(today_date, '竞价行情')
    df_yest = read_market_data(prev_date, '竞价行情')
    df_close = read_market_data(prev_date, '收盘行情')
    df_limit = read_market_data(prev_date, '收盘涨跌停')

    if df_today.empty or df_yest.empty:
        return pd.DataFrame()

    # 合并竞价金额并计算放量倍数
    df = df_today[['股票代码', '股票简称', '涨跌幅', '竞价金额']].copy()
    df = df.merge(df_yest[['股票代码', '竞价金额']], on='股票代码', suffixes=('_今', '_昨'), how='left')
    df['竞价金额_昨'] = df['竞价金额_昨'].fillna(1e6)  # 避免除0
    df['竞价放量倍数'] = df['竞价金额_今'] / df['竞价金额_昨']

    # 昨日形态判定
    if not df_close.empty:
        def yesterday_style(row):
            high = pd.to_numeric(row.get('最高价', 0), errors='coerce') or 0
            close = pd.to_numeric(row.get('收盘价', 0), errors='coerce') or 0
            limit = pd.to_numeric(row.get('涨停价', 0), errors='coerce') or 0
            pct = pd.to_numeric(row.get('涨跌幅', 0), errors='coerce') or 0
            if high >= limit > close:
                return '昨日炸板'
            # 2. 判断昨日大跌 (跌幅大于等于5%, 即 pct <= -5)
            elif pct <= -5:
                return '昨日大跌'
                
            # 3. 判断昨日大涨 (涨幅大于等于5%)
            elif pct >= 5:
                return '昨日大涨'
            return '普通震荡'

        df_close['昨日形态'] = df_close.apply(yesterday_style, axis=1)
        df = df.merge(df_close[['股票代码', '昨日形态']], on='股票代码', how='left')

    df['昨日形态'] = df['昨日形态'].fillna('普通震荡')

    # 连板信息
    if not df_limit.empty:
        df_limit = clean_dataframe(df_limit)
        df = df.merge(df_limit[['股票代码', '连续涨停天数', '涨停原因类别', '涨跌停']],
                      on='股票代码', how='left')

    df['连续涨停天数'] = pd.to_numeric(df['连续涨停天数'], errors='coerce').fillna(0).astype(int)

    # 预准备变量
    days = df['连续涨停天数']
    ratio = df['竞价放量倍数']
    style = df['昨日形态']
    amt = df['竞价金额_今']
    zt = df['涨跌停'].astype(str)
    pct = df['涨跌幅']

    tag_days = days.astype(str) + "板"
    
    conditions = [
        (pct >= 33),
        (zt.str.contains('跌停')),
        (days >= 2) & (ratio <= 0.85),
        (days >= 2) & (ratio >= 1.8),
        (days >= 2),
        (days == 1),
        (style == '昨日炸板') & (ratio >= 2.5) & (amt >= 5e6),
        (style == '昨日炸板'),
        (style == '昨日大涨') & (ratio >= 2.0),
        (style == '昨日大涨'),
        (style == '昨日大跌'),
        (ratio >= 3.0) & (amt >= 1e6),
        (ratio >= 2.5) & (amt >= 1e6)
    ]

    choices = [
        '新股', '昨日跌停',
        '缩量' + tag_days + '·筹码稳固',
        '巨量' + tag_days + '·筹码松动',
        '换手' + tag_days + '·健康',
        '昨日首板', '炸板·2.5倍量', '炸板不及2.5',
        '大涨非板·2倍以上', '大涨非板.小量','昨日大跌',
        '突发放量·观察', '活跃爆量'
    ]

    df['结构标签'] = np.select(conditions, choices, default="--")
    return df

def analyze_auction_flow(today_date: datetime, prev_date: datetime) -> Optional[Tuple[pd.DataFrame, Dict[str, Any]]]:
    """主分析：竞价资金流向 + 结构标签 + 题材标签"""
    df_today = read_market_data(today_date, '竞价行情')
    df_yest = read_market_data(prev_date, '竞价行情')
    if df_today.empty or df_yest.empty:
        return None

    # 基础金额统计
    total_today = df_today['竞价金额'].sum() / 1e8
    total_yest = df_yest['竞价金额'].sum() / 1e8
    net_change = total_today - total_yest
    ratio = total_today / total_yest - 1 if total_yest > 0 else 0
    
    def get_market_metrics(target_df):
        mask_not_st = ~target_df['股票简称'].str.contains('ST|st', na=False)
        t = target_df[mask_not_st].copy()
        
        # 情绪指标
        strong = (t['涨跌幅'] >= 7).sum()
        weak = (t['涨跌幅'] <= -7).sum()
        is_limit_up = (t['竞价价'] > 0) & (t['竞价价'] == t['涨停价'])
        is_limit_down = (t['竞价价'] > 0) & (t['竞价价'] == t['跌停价'])
        
        # 涨跌家数
        up_count = (t['涨跌幅'] > 0).sum()
        down_count = (t['涨跌幅'] < 0).sum()
        
        # 20cm 统计 (涨幅 > 19%)
        limit_up_20cm = (is_limit_up & (t['涨跌幅'] > 19)).sum()
        
        # 市场分类成交额 (元)
        sh_main_amt = t[t['股票代码'].str.startswith('sh6')]['竞价金额'].sum() / 1e8
        cyb_amt = t[t['股票代码'].str.startswith('sz3')]['竞价金额'].sum() / 1e8
        
        return {
            'strong': strong, 'weak': weak, 
            'limit_up': is_limit_up.sum(), 'limit_down': is_limit_down.sum(),
            'up_count': up_count, 'down_count': down_count,
            'limit_up_20cm': limit_up_20cm,
            'sh_main_amt': sh_main_amt, 'cyb_amt': cyb_amt
        }

    metrics_now = get_market_metrics(df_today)
    metrics_old = get_market_metrics(df_yest)

    overview = {
        'total_today': total_today, 'total_yest': total_yest,
        'net_change': net_change, 'ratio': ratio,
        'metrics_now': metrics_now, 'metrics_old': metrics_old
    }
    
    df = df_today[['股票代码', '股票简称', '涨跌幅', '竞价金额','竞价价', '涨停价', '昨收盘']].copy()
    df = df.merge(df_yest[['股票代码', '竞价金额']], on='股票代码', suffixes=('_今', '_昨'), how='outer')
    df['竞价金额_今'] = df['竞价金额_今'].fillna(0)
    df['竞价金额_昨'] = df['竞价金额_昨'].fillna(0)
    df['增量(亿)'] = (df['竞价金额_今'] - df['竞价金额_昨']) / 1e8
    
    # 注入结构标签
    df_tags = build_structure_tags(today_date, prev_date)
    if not df_tags.empty:
        df = df.merge(df_tags[['股票代码', '结构标签']], on='股票代码', how='left')
    df['结构标签'] = df['结构标签'].fillna('--')

    # 注入题材数据
    df_concept = load_concept_data()
    if not df_concept.empty:
        df['short_code'] = df['股票代码'].str.extract(r'(\d{6})')
        df = df.merge(df_concept, left_on='short_code', right_on='code', how='left')
        df[['所属概念', '所属行业']] = df[['所属概念', '所属行业']].fillna('')

        def match_hot(row):
            text = f"{row['所属行业']}|{row['所属概念']}"
            matched = [k for k in HOT_KEYWORDS if k in text]
            return " / ".join(matched)

        df['热点标签'] = df.apply(match_hot, axis=1)
    
    return df, overview

def calculate_hot_concepts(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """计算重点题材的统计数据"""
    if '所属概念' not in df.columns: return []
    
    stats = []
    df_c = df.copy()
    df_c['涨跌幅_num'] = pd.to_numeric(df_c['涨跌幅'], errors='coerce').fillna(0)
    
    for concept in HOT_CONCEPT_LIST:
        sub = df_c[df_c['所属概念'].str.contains(concept, na=False)].copy()
        if sub.empty: continue
        
        count = len(sub)
        red_ratio = (sub['涨跌幅_num'] > 0).mean() * 100
        net_inc = sub['增量(亿)'].sum()
        avg_pct = sub['涨跌幅_num'].mean()
        
        # 增量先锋
        leader = sub.nlargest(1, '增量(亿)')
        top_stock = f"{leader.iloc[0]['股票简称']}({leader.iloc[0]['涨跌幅']}%)" if not leader.empty else ""
        top_tag = leader.iloc[0]['结构标签'] if not leader.empty else ""
        
        # 异动明细
        sub['weight'] = sub['增量(亿)'] / (net_inc if net_inc > 0 else 1)
        active_mask = (sub['结构标签'] != '--') | (sub['涨跌幅_num'].abs() >= 5.0) | (sub['weight'] >= 0.20)
        active = sub[active_mask].sort_values('增量(亿)', ascending=False)
        
        detail = "无显著异动"
        if not active.empty:
            detail_list = []
            for _, r in active.head(5).iterrows():
                tag = r['结构标签']
                if tag == '--':
                    if r['涨跌幅_num'] >= 5: tag = "大幅拉升"
                    elif r['涨跌幅_num'] <= -5: tag = "大幅杀跌"
                    elif r['weight'] >= 0.2: tag = "吸金异常"
                detail_list.append(f"{r['股票简称']}({tag})")
            detail = " + ".join(detail_list)

        score = avg_pct * 3 + (net_inc * 0.5)
        stats.append({
            '热门概念': concept, '个股数': count, '红盘率%': round(red_ratio, 1),
            '平均涨跌%': round(avg_pct, 2), '增量(亿)': round(net_inc, 2),
            '强度得分': round(score, 2), '增量先锋': top_stock,
            '先锋标签': top_tag, '关键异动': detail
        })
    return stats

def calculate_auto_concepts(df: pd.DataFrame) -> pd.DataFrame:
    """自动识别并计算题材共振数据"""
    if df.empty or '所属概念' not in df.columns: return pd.DataFrame()

    df_c = df.copy()
    df_c['涨跌幅_num'] = pd.to_numeric(df_c['涨跌幅'], errors='coerce').fillna(0)
    df_c['tag_list'] = (df_c['所属概念'].fillna('') + ';' + df_c['所属行业'].fillna('')).str.replace('，', ';').str.split(';')
    
    exploded = df_c.explode('tag_list').rename(columns={'tag_list': '题材名称'})
    exploded = exploded[(~exploded['题材名称'].isin(BLACKLIST)) & (exploded['题材名称'].str.len() >= 2)]
    if exploded.empty: return pd.DataFrame()

    concept_grp = exploded.groupby('题材名称').agg(
        家数=('股票代码', 'count'),
        红盘率_val=('涨跌幅_num', lambda x: (x > 0).mean() * 100),
        平均涨跌_val=('涨跌幅_num', 'mean'),
        资金增量_亿=('增量(亿)', 'sum')
    )

    exploded['rank'] = exploded.groupby('题材名称')['增量(亿)'].rank(ascending=False, method='first')
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
    
    return final.sort_values('资金增量(亿)', ascending=False)


def build_zt_tags(today_date: datetime, prev_date: datetime) -> pd.DataFrame:
    """ 构建涨停标签分析表 - 金额单位：亿元 """
    # 1. 读取数据
    df_today = read_market_data(today_date, '竞价行情')
    df_concept = load_concept_data()
    
    if df_today.empty:
        return pd.DataFrame()


    # 修正了 numeric_check 里的逗号和列名
    numeric_check = ['涨停价', '竞价价', '买一价', '买一量', '卖一价', '卖一量', '流通市值', '涨跌幅']
    for col in numeric_check:
        if col in df_today.columns:
            df_today[col] = pd.to_numeric(df_today[col], errors='coerce').fillna(0)
    
    # 3. 筛选物理涨停 (竞价价 == 涨停价)
    mask_zt = (abs(df_today['涨停价'] - df_today['竞价价']) < 0.01) & (df_today['涨停价'] > 0)
    df_zt = df_today[mask_zt].copy()
    
    if df_zt.empty:
        return pd.DataFrame()
    
    # 4. 计算封单金额 (直接转换为 亿元)
    # 逻辑：(价格 * 股数) / 10^8
    has_valid_sell = (df_zt['卖一价'] > 0) & (df_zt['卖一量'] > 0)
    df_zt['封单额(亿)'] = np.where(
        has_valid_sell,
        -df_zt['卖一价'] * df_zt['卖一量'] / 100000000, # 压单为负
        df_zt['买一价'] * df_zt['买一量'] / 100000000   # 封单为正
    )

    # 5. 合并概念、行业及历史涨停原因
    if not df_concept.empty:
        # 统一代码格式
        c_code = 'code' if 'code' in df_concept.columns else '股票代码'
        df_concept[c_code] = df_concept[c_code].apply(standardize_code)
        # 选取的辅助分析列
        merge_cols = [c_code, '所属概念', '所属行业', '历史涨停原因类别']
        merge_cols = [c for c in merge_cols if c in df_concept.columns]
        
        df_zt = pd.merge(df_zt, df_concept[merge_cols], left_on='股票代码', right_on=c_code, how='left')
        
        # 匹配热点关键词
        df_zt['热点关键词'] = ""
        if '所属概念' in df_zt.columns:
            for keyword in HOT_KEYWORDS:
                mask = df_zt['所属概念'].astype(str).str.contains(keyword, na=False)
                df_zt.loc[mask, '热点关键词'] = df_zt.loc[mask, '热点关键词'].apply(
                    lambda x: keyword if x == "" else f"{x},{keyword}"
                )
    
    # 6. 市值处理
    if '流通市值' in df_zt.columns:
        df_zt['流通市值(亿)'] = df_zt['流通市值']

    # 7. 整理输出列
    output_cols = [
        '股票代码', '股票简称', '涨跌幅', '封单额(亿)', 
        '热点关键词', '所属行业', '流通市值(亿)', '历史涨停原因类别'
    ]
    final_cols = [col for col in output_cols if col in df_zt.columns]
    return df_zt[final_cols]
