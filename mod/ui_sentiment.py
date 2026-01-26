# -*- coding: utf-8 -*-
# modules/ui_sentiment.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def render_sentiment_dashboard(df: pd.DataFrame):
    """
    专门负责渲染“市场情绪”页面的所有 UI 逻辑
    """
    st.title("📊 市场情绪监控系统 (竞价 vs 收盘)")

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

    if df.empty:
        st.warning("暂无交易数据，请检查数据源。")
        return

    # 获取最新数据行和前一行用于对比
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    # --- 1. 竞价指标区 ---
    st.subheader("🚀 竞价核心情绪")
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        st.metric("竞价总额", f"{latest['竞价_总额']:.2f} 亿", delta=f"{latest['竞价_资金增减']:.2f} 亿")
    with col2:
        st.metric("全场涨跌比", f"{latest['竞价_全场涨跌比']:.2f}",
                  delta=f"{latest['竞价_全场涨跌比'] - prev['竞价_全场涨跌比']:.2f}")
    with col3:
        st.metric("上海涨跌比", f"{latest.get('竞价_上海涨跌比', 0):.2f}",
                  delta=f"{latest.get('竞价_上海差值', 0):+.2f} 亿")
    with col4:
        st.metric("创业涨跌比", f"{latest.get('竞价_创业涨跌比', 0):.2f}",
                  delta=f"{latest.get('竞价_创业差值', 0):+.2f} 亿")
    with col5:
        up = int(latest.get('竞价_涨停', 0))
        down = int(latest.get('竞价_跌停', 0))
        up_diff = int(latest.get('竞价_涨停_diff', 0))
        down_diff = int(latest.get('竞价_跌停_diff', 0))
        st.metric("竞价涨/跌停", f"{up} / {down}", delta=f"{up_diff:+d} / {down_diff:+d}")
    with col6:
        strong = int(latest.get('竞价_强力', 0))
        weak = int(latest.get('竞价_极弱', 0))
        s_diff = int(latest.get('竞价_强力_diff', 0))
        w_diff = int(latest.get('竞价_极弱_diff', 0))
        st.metric("竞价强力|弱力", f"{strong}  / {weak}", delta=f"{s_diff:+d}  / {w_diff:+d}")

    # --- 2. 收盘指标区 ---
    if '收盘_总额' in df.columns and not pd.isna(latest['收盘_总额']):
        st.divider()
        st.subheader("🏁 收盘核心情绪")
        sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)

        with sc1:
            st.metric("收盘总额", f"{latest['收盘_总额']:.2f} 亿", delta=f"{latest['收盘_资金增减']:.2f} 亿")
        with sc2:
            repair = latest['收盘_全场涨跌比'] - latest['竞价_全场涨跌比']
            st.metric("收盘涨跌比", f"{latest['收盘_全场涨跌比']:.2f}", delta=f" {repair:.2f}盘中")
        with sc3:
            st.metric("上海涨跌比", f"{latest.get('收盘_上海涨跌比', 0):.2f}",
                      delta=f"{latest.get('收盘_上海差值', 0):+.2f} 亿")
        with sc4:
            st.metric("创业涨跌比", f"{latest.get('收盘_创业涨跌比', 0):.2f}",
                      delta=f"{latest.get('收盘_创业差值', 0):+.2f} 亿")
        with sc5:
            up = int(latest.get('收盘_涨停', 0))
            down = int(latest.get('收盘_跌停', 0))
            up_diff = int(latest.get('收盘_涨停_diff', 0))
            down_diff = int(latest.get('收盘_跌停_diff', 0))
            st.metric("收盘涨/跌停", f"{up} / {down}", delta=f"{up_diff:+d} / {down_diff:+d}")
        with sc6:
            strong = int(latest.get('收盘_强力', 0))
            weak = int(latest.get('收盘_极弱', 0))
            s_diff = int(latest.get('收盘_强力_diff', 0))
            w_diff = int(latest.get('收盘_极弱_diff', 0))
            st.metric("收盘强力|弱力", f"{strong}  / {weak}", delta=f"{s_diff:+d}  / {w_diff:+d}")
    else:
        st.info("💡 当前为早盘阶段，收盘数据尚未同步。")

    st.divider()

    # --- 3. 趋势图 ---
    st.subheader("📈 趋势可视化 (金额与三线情绪共振)")
    mode = st.radio("切换趋势维度", ["竞价情绪趋势", "收盘情绪趋势"], horizontal=True, key="trend_mode")
    prefix = "竞价" if "竞价" in mode else "收盘"

    if f"{prefix}_总额" in df.columns:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(x=df['日期'], y=df[f'{prefix}_总额'], name="总额(亿)", marker_color='rgba(100, 149, 237, 0.6)'),
            secondary_y=False)
        fig.add_trace(go.Scatter(x=df['日期'], y=df[f'{prefix}_全场涨跌比'], name="全场涨跌比",
                                 line=dict(color='firebrick', width=3)), secondary_y=True)
        fig.add_trace(go.Scatter(x=df['日期'], y=df[f'{prefix}_创业涨跌比'], name="创业板涨跌比",
                                 line=dict(color='royalblue', width=2, dash='dot')), secondary_y=True)

        fig.update_layout(
            height=500,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
            margin=dict(l=10, r=10, t=50, b=10)
        )
        fig.update_xaxes(type='category')

        # 并排显示逻辑
        show_combined = st.checkbox("并排显示：合并图（竞价/收盘 资金增减 + 涨跌比）", value=False)
        if show_combined:
            fig2 = make_subplots(specs=[[{"secondary_y": True}]])
            if '竞价_资金增减' in df.columns:
                fig2.add_trace(go.Bar(x=df['日期'], y=df['竞价_资金增减'], name='竞价资金增减(亿)',
                                      marker_color='rgba(55, 128, 191, 0.7)'), secondary_y=False)
            if '收盘_资金增减' in df.columns:
                fig2.add_trace(go.Bar(x=df['日期'], y=df['收盘_资金增减'], name='收盘资金增减(亿)',
                                      marker_color='rgba(26, 118, 255, 0.5)'), secondary_y=False)

            if '竞价_全场涨跌比' in df.columns:
                fig2.add_trace(
                    go.Scatter(x=df['日期'], y=df['竞价_全场涨跌比'], name='竞价涨跌比', mode='lines+markers',
                               line=dict(color='firebrick', width=2)), secondary_y=True)
            if '收盘_全场涨跌比' in df.columns:
                fig2.add_trace(
                    go.Scatter(x=df['日期'], y=df['收盘_全场涨跌比'], name='收盘涨跌比', mode='lines+markers',
                               line=dict(color='royalblue', width=2, dash='dot')), secondary_y=True)

            fig2.update_layout(title_text=f"合并：资金增减(亿) 与 涨跌比", height=500, hovermode='x unified',
                               barmode='group',
                               legend=dict(orientation='h', yanchor='bottom', y=1.05, xanchor='center', x=0.5))
            fig2.update_xaxes(type='category')
            l_col, r_col = st.columns(2)
            l_col.plotly_chart(fig, use_container_width=True)
            r_col.plotly_chart(fig2, use_container_width=True)
        else:
            st.plotly_chart(fig, use_container_width=True)

    # --- 4. 统计表格 ---
    st.subheader("📋 详细统计数据")
    cols = ['日期', f'{prefix}_总额', f'{prefix}_资金增减', f'{prefix}_全场涨跌比', f'{prefix}_强力', f'{prefix}_极弱',
            f'{prefix}_涨停', f'{prefix}_跌停']
    valid_cols = [c for c in cols if c in df.columns]

    st.dataframe(
        df[valid_cols].sort_values('日期', ascending=False).style.format({
            f'{prefix}_总额': "{:.2f}", f'{prefix}_资金增减': "{:+.2f}", f'{prefix}_全场涨跌比': "{:.2f}"
        }).background_gradient(subset=[f'{prefix}_全场涨跌比'], cmap='RdYlGn'),
        use_container_width=True
    )

    with st.expander("🔍 查看原始数据明细"):
        st.dataframe(df.sort_values('日期', ascending=False), use_container_width=True)

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
                    fig_custom.add_trace(go.Bar(x=df['日期'], y=y, name=colname, marker_color=colors[colname]),
                                         secondary_y=is_sec)
                else:
                    fig_custom.add_trace(go.Scatter(x=df['日期'], y=y, name=colname, line=dict(color=colors[colname])),
                                         secondary_y=is_sec)
            fig_custom.update_layout(height=550, hovermode='x unified',
                                     legend=dict(orientation='h', x=0.5, xanchor='center'))
            fig_custom.update_xaxes(type='category')
            st.plotly_chart(fig_custom, use_container_width=True)
