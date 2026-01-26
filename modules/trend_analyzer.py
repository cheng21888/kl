# modules/trend_analyzer.py
import pandas as pd
import os
import streamlit as st
import plotly.graph_objects as go
from modules.data_loader import get_trade_dates, read_market_data
from modules.utils import standardize_code
from modules.analyzer import build_structure_tags

# --- 优化点 4: 使用 nlargest 和向量化计算 ---
def calculate_top_amount_percentage(df, type_prefix, top_n=15):
    """计算前N占比，优化了排序性能和单位转换速度"""
    amt_col = f"{type_prefix}金额"
    
    if df.empty or amt_col not in df.columns:
        return None, pd.DataFrame()
    
    # 1. 向量化转换为数值
    df[amt_col] = pd.to_numeric(df[amt_col], errors='coerce').fillna(0)
    
    # 2. 预先标准化代码 (存入临时列，避免在后续循环中反复调用函数)
    if '股票代码' in df.columns:
        df['std_code'] = df['股票代码'].apply(standardize_code)
    
    # 3. 统一转换为“亿元”单位 (向量化判定)
    max_val = df[amt_col].max()
    if max_val > 10000000:       # 原始为“元”
        df[amt_col] = df[amt_col] / 100000000
    elif 0 < max_val < 1000000:  # 原始为“万”
        df[amt_col] = df[amt_col] / 10000
    
    total_amount = df[amt_col].sum()
    if total_amount == 0:
        return None, pd.DataFrame()

    # 4. 使用 nlargest 代替 sort_values.head(n)，在取少量最大值时效率更高
    df_top = df.nlargest(top_n, amt_col).copy()
    
    # 5. 格式化数值精度
    df_top[amt_col] = df_top[amt_col].round(2)
    if '涨跌幅' in df_top.columns:
        df_top['涨跌幅'] = pd.to_numeric(df_top['涨跌幅'], errors='coerce').fillna(0).round(2)
    
    top_amount = df_top[amt_col].sum()
    return (top_amount / total_amount) * 100, df_top

# --- 优化点 3: 增加缓存装饰器 ---
@st.cache_data(ttl=3600) # 缓存1小时，相同日期请求秒回
def analyze_and_plot_top_stocks_trend(today_date, num_days=30):
    """生成趋势图数据和今日详情，优化了连续天数的计算逻辑"""
    all_dates = get_trade_dates(count=60) # 取多一点确保有足够日期回溯
    recent_dates = [d for d in all_dates if d <= today_date][-num_days:]

    plot_data = []
    # 存储每日Top15的代码集合，用于极速计算连续天数
    auc_history_sets = {} 
    cls_history_sets = {}
    
    current_day_auc = pd.DataFrame()
    current_day_cls = pd.DataFrame()

    # 1. 遍历日期，收集数据
    for d in recent_dates:
        df_auction = read_market_data(d, '竞价行情')
        df_close = read_market_data(d, '收盘行情')

        auc_p, df_auc_t = calculate_top_amount_percentage(df_auction, "竞价")
        cls_p, df_cls_t = calculate_top_amount_percentage(df_close, "收盘")

        if auc_p is not None:
            plot_data.append({'date': d, 'auc': auc_p, 'cls': cls_p})
            # 记录标准化代码集合
            auc_history_sets[d] = set(df_auc_t['std_code'])
            if d == today_date: current_day_auc = df_auc_t
            
        if cls_p is not None:
            cls_history_sets[d] = set(df_cls_t['std_code'])
            if d == today_date: current_day_cls = df_cls_t

    # 2. 优化连续天数计算 (减少 standardize_code 调用)
    sorted_dates_desc = sorted(recent_dates, reverse=True)

    def get_streak(std_code, history_dict):
        streak = 0
        for d in sorted_dates_desc:
            if std_code in history_dict.get(d, set()):
                streak += 1
            else:
                break
        return streak

    if not current_day_auc.empty:
        current_day_auc['连续天数'] = current_day_auc['std_code'].apply(lambda x: get_streak(x, auc_history_sets))
    if not current_day_cls.empty:
        current_day_cls['连续天数'] = current_day_cls['std_code'].apply(lambda x: get_streak(x, cls_history_sets))

    # 3. 绘图逻辑
    fig = None
    if plot_data:
        pdf = pd.DataFrame(plot_data)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=pdf['date'], y=pdf['auc'], mode='lines+markers', name='竞价Top15占比', line=dict(color='#EF5350', width=2)))
        fig.add_trace(go.Scatter(x=pdf['date'], y=pdf['cls'], mode='lines+markers', name='收盘Top15占比', line=dict(color='#42A5F5', width=2)))
        fig.update_layout(
            title=dict(text="市场集中度趋势 (Top15成交额占比)", x=0.5),
            xaxis_title="交易日", yaxis_title="占比 (%)",
            yaxis=dict(ticksuffix="%"), hovermode="x unified",
            height=380, template="plotly_white", margin=dict(l=20, r=20, t=50, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

    return fig, current_day_auc, current_day_cls

def style_market_table(df, type_prefix):
    """表格美化"""
    amt_col = f"{type_prefix}金额"
    
    # 样式函数
    def color_pct(val):
        if val > 0: return 'color: #ef5350; font-weight: bold'
        if val < 0: return 'color: #66bb6a; font-weight: bold'
        return 'color: gray'

    def color_count(val):
        if val >= 5: return 'background-color: #ff4b4b; color: white'
        if val >= 3: return 'background-color: #ff8a80'
        if val >= 2: return 'background-color: #fff9c4'
        return ''

    cols = ['股票代码', '股票简称', amt_col, '涨跌幅', '连续天数', '结构标签']
    valid_cols = [c for c in cols if c in df.columns]
    
    styler = df[valid_cols].style
    if '涨跌幅' in valid_cols:
        styler = styler.map(color_pct, subset=['涨跌幅'])
    if '连续天数' in valid_cols:
        styler = styler.map(color_count, subset=['连续天数'])
        
    return styler.format({amt_col: "{:.2f} 亿", "涨跌幅": "{:+.2f}%"})

def display_trend_analysis(selected_date):
    """主渲染函数"""
    st.subheader(f"📊 市场集中度与个股趋势 ({selected_date.strftime('%Y-%m-%d')})")
    
    # 1. 执行计算（受缓存保护）
    fig, df_auc, df_cls = analyze_and_plot_top_stocks_trend(selected_date)
    
    # 2. 注入结构标签 (仅针对当前页面的 Top15 股票进行 Merge，极快)
    try:
        all_dates = get_trade_dates(count=40)
        curr_idx = all_dates.index(selected_date)
        prev_date = all_dates[curr_idx - 1] if curr_idx > 0 else None
        
        if prev_date:
            # 这里的 build_structure_tags 建议也加上 @st.cache_data
            tags_df = build_structure_tags(selected_date, prev_date)
            if not tags_df.empty:
                tags_subset = tags_df[['股票代码', '结构标签']]
                if not df_auc.empty:
                    df_auc = df_auc.merge(tags_subset, on='股票代码', how='left').fillna('')
                if not df_cls.empty:
                    df_cls = df_cls.merge(tags_subset, on='股票代码', how='left').fillna('')
    except Exception as e:
        pass

    # 3. 渲染图表
    if fig:
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    
    # 4. 渲染双栏表格
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🔴 竞价成交额 Top15")
        if not df_auc.empty:
            st.dataframe(style_market_table(df_auc, "竞价"), use_container_width=True, height=550)
        else:
            st.info("暂无数据")
            
    with col2:
        st.markdown("#### 🔵 收盘成交额 Top15")
        if not df_cls.empty:
            st.dataframe(style_market_table(df_cls, "收盘"), use_container_width=True, height=550)
        else:
            st.info("暂无数据")
