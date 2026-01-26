# modules/ui_top_stocks.py
import streamlit as st
import pandas as pd
from modules.data_loader import read_market_data

def render_top_turnover_page(target_date_obj):
    st.header(f"🏆 成交额活跃榜单 ({target_date_obj.strftime('%Y-%m-%d')})")
    
    # 1. 读取数据
    df_jj = read_market_data(target_date_obj, '竞价行情')
    df_sp = read_market_data(target_date_obj, '收盘行情')
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🔥 竞价成交额 Top 15")
        if not df_jj.empty:
            # 确保列名统一
            df_jj_top = df_jj.sort_values('竞价金额', ascending=False).head(15)
            # 整理显示列
            display_cols = ['股票代码', '股票简称', '竞价金额', '涨跌幅', '竞价价']
            st.dataframe(df_jj_top[[c for c in display_cols if c in df_jj_top.columns]], use_container_width=True)
        else:
            st.info("暂无竞价数据")

    with col2:
        st.subheader("💰 收盘成交额 Top 15")
        if not df_sp.empty:
            df_sp_top = df_sp.sort_values('收盘金额', ascending=False).head(15)
            display_cols = ['股票代码', '股票简称', '收盘金额', '涨跌幅', '收盘价']
            st.dataframe(df_sp_top[[c for c in display_cols if c in df_sp_top.columns]], use_container_width=True)
        else:
            st.info("暂无收盘数据")

    st.divider()
    
    # 2. 多日拼接逻辑 (简单示例)
    st.subheader("📅 近期成交额对比 (拼接统计)")
    lookback = st.slider("选择对比天数", 2, 10, 5)
    from modules.data_loader import get_trade_dates
    dates = get_trade_dates(lookback)
    
    combined_data = []
    for d in dates:
        tmp_df = read_market_data(d, '收盘行情')
        if not tmp_df.empty:
            total_amt = tmp_df['收盘金额'].sum() / 1e8
            combined_data.append({"日期": d.strftime('%Y-%m-%d'), "总成交额(亿)": total_amt})
    
    if combined_data:
        st.line_chart(pd.DataFrame(combined_data).set_index("日期"))
