# -*- coding: utf-8 -*-
# modules/ui_sentiment_v2.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def render_sentiment_dashboard(df: pd.DataFrame):
    """
    专门负责渲染“市场情绪”页面的所有 UI 逻辑
    """
    # 保证数据是可写的
    df = df.copy()

    # 2. 物理抹除逻辑
    for p in ['竞价', '收盘']:
        # 检查总额是否为 0 或 NaN
        # 只要总额是 0，就意味着该时段还没发生，把所有相关列的数据全部物理设为 None
        mask = (df[f'{p}_总额'] <= 0) | (df[f'{p}_总额'].isna())
        
        related_cols = [c for c in df.columns if c.startswith(f'{p}_')]
        
        # 关键操作：直接设为 None。这在 pandas 中相当于物理抹除了该单元格的数据
        df.loc[mask, related_cols] = None

    # --- 后续逻辑完全不动 ---
    if df.empty:
        st.warning("暂无交易数据。")
        return

    # 获取最新数据行和前一行用于对比
    latest = df.iloc[-1]

    prev = df.iloc[-2] if len(df) > 1 else latest
    
    # --- 1. 竞价指标区 ---
    st.subheader("🚀 竞价核心情绪")
    
    # 使用容器创建卡片效果
    with st.container():
        # 更合理的列宽分配
        cols = st.columns([1.2, 1, 1, 1, 1.1, 1.1], gap="small")
        
        with cols[0]:
            st.metric("竞价总额", f"{latest['竞价_总额']:.2f} 亿", delta=f"{latest['竞价_资金增减']:.2f} 亿", label_visibility="visible")
        with cols[1]:
            st.metric("全场涨跌比", f"{latest['竞价_全场涨跌比']:.2f}", 
                      delta=f"{latest['竞价_全场涨跌比'] - prev['竞价_全场涨跌比']:.2f}", label_visibility="visible")
        with cols[2]:
            st.metric("上海涨跌比", f"{latest.get('竞价_上海涨跌比', 0):.2f}", 
                      delta=f"{latest.get('竞价_上海差值', 0):+.2f} 亿", label_visibility="visible")
        with cols[3]:
            st.metric("创业涨跌比", f"{latest.get('竞价_创业涨跌比', 0):.2f}", 
                      delta=f"{latest.get('竞价_创业差值', 0):+.2f} 亿", label_visibility="visible")
        with cols[4]:
            up = int(latest.get('竞价_涨停', 0))
            down = int(latest.get('竞价_跌停', 0))
            up_diff = int(latest.get('竞价_涨停_diff', 0))
            down_diff = int(latest.get('竞价_跌停_diff', 0))
            st.metric("竞价涨/跌停", f"{up} / {down}", delta=f"{up_diff:+d} / {down_diff:+d}", label_visibility="visible")
        with cols[5]:
            strong = int(latest.get('竞价_强力', 0))
            weak = int(latest.get('竞价_极弱', 0))
            s_diff = int(latest.get('竞价_强力_diff', 0))
            w_diff = int(latest.get('竞价_极弱_diff', 0))
            st.metric("竞价强力|弱力", f"{strong} / {weak}", delta=f"{s_diff:+d} / {w_diff:+d}", label_visibility="visible")

    # --- 2. 收盘指标区 ---
    if '收盘_总额' in df.columns and not pd.isna(latest['收盘_总额']):
        st.divider()
        st.subheader("🏁 收盘核心情绪")
        
        with st.container():
            # 更合理的列宽分配
            cols = st.columns([1.2, 1, 1, 1, 1.1, 1.1], gap="small")
            
            with cols[0]:
                st.metric("收盘总额", f"{latest['收盘_总额']:.2f} 亿", delta=f"{latest['收盘_资金增减']:.2f} 亿", label_visibility="visible")
            with cols[1]:
                repair = latest['收盘_全场涨跌比'] - latest['竞价_全场涨跌比']
                st.metric("收盘涨跌比", f"{latest['收盘_全场涨跌比']:.2f}", delta=f" {repair:.2f}盘中", label_visibility="visible")
            with cols[2]:
                st.metric("上海涨跌比", f"{latest.get('收盘_上海涨跌比', 0):.2f}", 
                          delta=f"{latest.get('收盘_上海差值', 0):+.2f} 亿", label_visibility="visible")
            with cols[3]:
                st.metric("创业涨跌比", f"{latest.get('收盘_创业涨跌比', 0):.2f}", 
                          delta=f"{latest.get('收盘_创业差值', 0):+.2f} 亿", label_visibility="visible")
            with cols[4]:
                up = int(latest.get('收盘_涨停', 0))
                down = int(latest.get('收盘_跌停', 0))
                up_diff = int(latest.get('收盘_涨停_diff', 0))
                down_diff = int(latest.get('收盘_跌停_diff', 0))
                st.metric("收盘涨/跌停", f"{up} / {down}", delta=f"{up_diff:+d} / {down_diff:+d}", label_visibility="visible")
            with cols[5]:
                strong = int(latest.get('收盘_强力', 0))
                weak = int(latest.get('收盘_极弱', 0))
                s_diff = int(latest.get('收盘_强力_diff', 0))
                w_diff = int(latest.get('收盘_极弱_diff', 0))
                st.metric("收盘强力|弱力", f"{strong} / {weak}", delta=f"{s_diff:+d} / {w_diff:+d}", label_visibility="visible")
    else:
        st.info("💡 当前为早盘阶段，收盘数据尚未同步。")

    st.divider()

    # --- 3. 趋势分析 ---
    st.subheader("📈 趋势分析")
    
    # 选择图表类型
    chart_type = st.radio(
        "选择图表类型",
        [
            "竞价总额与涨跌比",
            "收盘总额与涨跌比",
            "15占比竞价与收盘",
            "强弱股趋势"
        ],
        horizontal=True,
        key="chart_type"
    )
    
    # 绘制图表
    if chart_type == "竞价总额与涨跌比":
        # 竞价总额与涨跌比
        if all(col in df.columns for col in ['竞价_总额', '竞价_全场涨跌比', '竞价_上海涨跌比', '竞价_创业涨跌比']):
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            # 总额柱状图
            fig.add_trace(go.Bar(x=df['日期'], y=df['竞价_总额'], name="竞价总额(亿)", marker_color='rgba(100, 149, 237, 0.6)'), secondary_y=False)
            # 涨跌比线图
            fig.add_trace(go.Scatter(x=df['日期'], y=df['竞价_全场涨跌比'], name="全场涨跌比", line=dict(color='firebrick', width=3)), secondary_y=True)
            fig.add_trace(go.Scatter(x=df['日期'], y=df['竞价_上海涨跌比'], name="上海涨跌比", line=dict(color='green', width=2, dash='dot')), secondary_y=True)
            fig.add_trace(go.Scatter(x=df['日期'], y=df['竞价_创业涨跌比'], name="创业涨跌比", line=dict(color='royalblue', width=2, dash='3px,2px')), secondary_y=True)

            fig.update_layout(
                height=500, 
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
                margin=dict(l=10, r=10, t=50, b=10)
            )
            fig.update_xaxes(type='category')
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("💡 数据不足，无法绘制竞价总额与涨跌比图表")
            
    elif chart_type == "收盘总额与涨跌比":
        # 收盘总额与涨跌比
        if all(col in df.columns for col in ['收盘_总额', '收盘_全场涨跌比', '收盘_上海涨跌比', '收盘_创业涨跌比']):
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            # 总额柱状图
            fig.add_trace(go.Bar(x=df['日期'], y=df['收盘_总额'], name="收盘总额(亿)", marker_color='rgba(100, 149, 237, 0.6)'), secondary_y=False)
            # 涨跌比线图
            fig.add_trace(go.Scatter(x=df['日期'], y=df['收盘_全场涨跌比'], name="全场涨跌比", line=dict(color='firebrick', width=3)), secondary_y=True)
            fig.add_trace(go.Scatter(x=df['日期'], y=df['收盘_上海涨跌比'], name="上海涨跌比", line=dict(color='green', width=2, dash='dot')), secondary_y=True)
            fig.add_trace(go.Scatter(x=df['日期'], y=df['收盘_创业涨跌比'], name="创业涨跌比", line=dict(color='royalblue', width=2, dash='3px,2px')), secondary_y=True)

            fig.update_layout(
                height=500, 
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
                margin=dict(l=10, r=10, t=50, b=10)
            )
            fig.update_xaxes(type='category')
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("💡 数据不足，无法绘制收盘总额与涨跌比图表")
            
    elif chart_type == "15占比竞价与收盘":
        # 15占比竞价与收盘
        if all(col in df.columns for col in ['竞价_前15占比', '收盘_前15占比']):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df['日期'], y=df['竞价_前15占比'], name="竞价前15占比", line=dict(color='blue', width=3)))
            fig.add_trace(go.Scatter(x=df['日期'], y=df['收盘_前15占比'], name="收盘前15占比", line=dict(color='firebrick', width=3)))

            fig.update_layout(
                height=500, 
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
                margin=dict(l=10, r=10, t=50, b=10)
            )
            fig.update_xaxes(type='category')
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("💡 数据不足，无法绘制前15占比图表")
            
    elif chart_type == "强弱股趋势":
        # 强弱股趋势
        if all(col in df.columns for col in ['竞价_强力', '竞价_极弱', '收盘_强力', '收盘_极弱']):
            fig = make_subplots(rows=2, cols=1, subplot_titles=["竞价强弱股", "收盘强弱股"])
            # 竞价强弱股
            fig.add_trace(go.Bar(x=df['日期'], y=df['竞价_强力'], name="竞价强力", marker_color='firebrick'), row=1, col=1)
            fig.add_trace(go.Bar(x=df['日期'], y=df['竞价_极弱'], name="竞价极弱", marker_color='green'), row=1, col=1)
            # 收盘强弱股
            fig.add_trace(go.Bar(x=df['日期'], y=df['收盘_强力'], name="收盘强力", marker_color='firebrick'), row=2, col=1)
            fig.add_trace(go.Bar(x=df['日期'], y=df['收盘_极弱'], name="收盘极弱", marker_color='green'), row=2, col=1)

            fig.update_layout(
                height=600, 
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
                margin=dict(l=10, r=10, t=100, b=10)
            )
            fig.update_xaxes(type='category', row=1, col=1)
            fig.update_xaxes(type='category', row=2, col=1)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("💡 数据不足，无法绘制强弱股趋势图表")

    # 移除详细统计数据的显示

    with st.expander("🔍 查看原始数据明细"):
        st.dataframe(df.sort_values('日期', ascending=False), width='stretch')

    # --- 5. 自定义绘图区 ---
    st.markdown("---")
    st.subheader("📊 自定义绘图")
    plot_columns_options = [c for c in df.columns if c != '日期']
    if plot_columns_options:
        cols_to_plot = st.multiselect("选择要绘制的列", plot_columns_options, default=plot_columns_options[:1])
        palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
        colors, types, axis_map = {}, {}, {}
        
        for i, colname in enumerate(cols_to_plot):
            a, b, c = st.columns([1, 1, 1])
            with a: colors[colname] = st.color_picker(f"{colname} 颜色", palette[i % len(palette)], key=f"cp_{colname}")
            with b: types[colname] = st.selectbox(f"{colname} 类型", ["折线图", "柱状图"], key=f"tp_{colname}")
            with c: axis_map[colname] = st.selectbox(f"{colname} 轴", ["主轴", "次轴"], key=f"ax_{colname}")

        if cols_to_plot:
            fig_custom = make_subplots(specs=[[{"secondary_y": True}]])
            for colname in cols_to_plot:
                y = df[colname]
                is_sec = (axis_map[colname] == '次轴')
                if types[colname] == '柱状图':
                    fig_custom.add_trace(go.Bar(x=df['日期'], y=y, name=colname, marker_color=colors[colname]), secondary_y=is_sec)
                else:
                    fig_custom.add_trace(go.Scatter(x=df['日期'], y=y, name=colname, line=dict(color=colors[colname])), secondary_y=is_sec)
            fig_custom.update_layout(height=550, hovermode='x unified', legend=dict(orientation='h', x=0.5, xanchor='center'))
            fig_custom.update_xaxes(type='category')
            st.plotly_chart(fig_custom, width='stretch')
