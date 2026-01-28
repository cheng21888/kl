import streamlit as st
import pandas as pd
import os
from datetime import datetime
from modules.data_loader import read_market_data
from modules.config import DATA_DIR

st.set_page_config(page_title="股票竞价收盘分析看板", layout="wide")

st.title("📈 股票竞价收盘分析看板")

# 1. 侧边栏：选择日期和类型
st.sidebar.header("查询配置")

# 获取 data/raw 下的所有日期
if os.path.exists(DATA_DIR):
    files = os.listdir(DATA_DIR)
    dates = sorted(list(set([f.split('_')[0] for f in files if '_' in f])), reverse=True)
else:
    dates = []

if not dates:
    st.warning("⚠️ 未在 data/raw 目录下找到数据文件，请先运行采集脚本。")
else:
    selected_date_str = st.sidebar.selectbox("选择日期", dates)
    selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d")
    
    data_type = st.sidebar.radio("选择数据类型", ["竞价行情", "收盘行情", "竞价指数", "收盘指数", "竞价涨跌停", "收盘涨跌停"])

    # 2. 加载数据
    try:
        df = read_market_data(selected_date, data_type)
        
        if df.empty:
            st.info(f"📅 {selected_date_str} 的 {data_type} 数据为空或未找到。")
        else:
            st.subheader(f"📊 {selected_date_str} - {data_type}")
            
            # 3. 数据统计概览
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("总样本数", len(df))
            
            if '涨跌幅' in df.columns:
                with col2:
                    avg_pct = df['涨跌幅'].mean()
                    st.metric("平均涨跌幅", f"{avg_pct:.2f}%")
                with col3:
                    up_count = len(df[df['涨跌幅'] > 0])
                    st.metric("上涨家数", up_count)

            # 4. 数据表格展示
            st.dataframe(df, use_container_width=True)
            
            # 5. 简单可视化
            if '涨跌幅' in df.columns:
                st.subheader("涨跌幅分布图")
                hist_values = df['涨跌幅'].dropna()
                st.bar_chart(hist_values)

    except Exception as e:
        st.error(f"❌ 加载数据出错: {e}")

st.sidebar.markdown("---")
st.sidebar.info("数据由 GitHub Actions 自动采集并保存至 data/raw 目录。")
