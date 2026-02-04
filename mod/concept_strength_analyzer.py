# -*- coding: utf-8 -*-
# concept_strength_analyzer.py
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta


# ===================== 内置工具函数（保障数据读取/处理健壮性）=====================
def standardize_code(code):
    """标准化股票代码为6位字符串，处理空值/非数字/带市场标识的情况"""
    if pd.isna(code):
        return ""
    code_str = str(code).strip()
    code_digit = ''.join([c for c in code_str if c.isdigit()])
    return code_digit if len(code_digit) == 6 else ""


def safe_read_csv(file_path, encoding="utf-8", sep=",", **kwargs):
    """安全读取CSV，含编码兼容、异常处理、股票代码标准化、重复列预处理"""
    if not os.path.exists(file_path):
        print(f"警告：文件不存在 - {file_path}")
        return pd.DataFrame()
    if os.path.getsize(file_path) == 0:
        print(f"警告：空文件 - {file_path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(file_path, encoding=encoding, sep=sep, **kwargs)
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding="gbk", sep=sep, **kwargs)
    except Exception as e:
        print(f"读取文件失败 {file_path}，错误：{str(e)}")
        return pd.DataFrame()

    # 预处理：删除完全重复的列，从源头避免冲突
    df = df.loc[:, ~df.columns.duplicated()]
    # 标准化code列并强制转为字符串
    if "code" in df.columns:
        df["code"] = df["code"].apply(standardize_code).astype(str)
        df = df[df["code"] != ""]
    # 标准化概念映射表的「股票代码」列
    if "股票代码" in df.columns:
        df["股票代码"] = df["股票代码"].apply(standardize_code).astype(str)
        df = df[df["股票代码"] != ""]

    return df.reset_index(drop=True)


def drop_duplicate_columns(df, keep_first=True):
    """通用重复列删除函数，保障列名唯一性"""
    if df.empty:
        return df
    keep_col = ~df.columns.duplicated(keep='first' if keep_first else 'last')
    df_clean = df.loc[:, keep_col]
    duplicate_cols = df.columns[df.columns.duplicated()].tolist()
    if duplicate_cols:
        print(f"提示：检测到重复列并删除 - {duplicate_cols}")
    return df_clean


# ===================== 核心函数：按涨幅达标家数排序（贴合需求）=====================
def calculate_concept_strength(target_date, data_path="./data/raw", metadata_path="./metadata"):
    """
    核心逻辑：先筛涨跌幅>9/7%股票 → 匹配所属概念 → 按概念达标家数降序排序
    :param target_date: 目标日期 (datetime.date)
    :return: 涨幅>9%家数排名DF、涨幅>7%家数排名DF、达标股票所属的所有概念集合
    """
    target_date_str = target_date.strftime('%Y-%m-%d')
    # 1. 读取当日竞价行情数据并预处理
    daily_file = f"{target_date_str}_竞价行情.csv"
    daily_df = safe_read_csv(os.path.join(data_path, daily_file))
    daily_df = drop_duplicate_columns(daily_df)
    if daily_df.empty or not all(col in daily_df.columns for col in ["code", "now", "close"]):
        print("警告：竞价行情数据为空或缺少核心列（code/now/close）")
        return pd.DataFrame(), pd.DataFrame(), set()

    # 2. 计算涨跌幅（防除零错误，过滤close为空/0的无效数据）
    daily_df = daily_df[(~pd.isna(daily_df["close"])) & (daily_df["close"] != 0)].copy()
    daily_df["涨跌幅"] = (daily_df["now"] / daily_df["close"]) - 1  # 涨跌幅=（当前价/昨收价）-1
    print(f"提示：当日有效竞价股票总数 - {len(daily_df)}")

    # 3. 核心步骤1：筛选涨跌幅>9%和>7%的股票（先筛选，再匹配概念，提升效率）
    df_gt9 = daily_df[daily_df["涨跌幅"] > 0.09].copy()  # 涨跌幅>9%的股票
    df_gt7 = daily_df[daily_df["涨跌幅"] > 0.07].copy()  # 涨跌幅>7%的股票
    print(f"提示：涨跌幅>9%的股票数 - {len(df_gt9)}；涨跌幅>7%的股票数 - {len(df_gt7)}")
    if len(df_gt9) == 0 and len(df_gt7) == 0:
        print("警告：当日无涨跌幅>7%的股票，无法计算概念强度")
        return pd.DataFrame(), pd.DataFrame(), set()

    # 4. 读取概念映射表并预处理（统一列名+类型，保障合并无冲突）
    concept_df = safe_read_csv(os.path.join(metadata_path, "所属概念.csv"))
    concept_df = drop_duplicate_columns(concept_df)
    required_cols = ["股票代码", "所属概念"]
    if concept_df.empty or not all(col in concept_df.columns for col in required_cols):
        print(f"警告：概念映射表异常，需包含列 {required_cols}")
        return pd.DataFrame(), pd.DataFrame(), set()
    # 重命名为code，与行情表列名统一，仅保留必要列
    concept_df = concept_df[required_cols].rename(columns={"股票代码": "code"}).copy()
    concept_df["code"] = concept_df["code"].astype(str)

    # 5. 核心步骤2：为达标股票匹配所属概念
    df_gt9_with_concept = pd.merge(df_gt9, concept_df, on="code", how="inner")
    df_gt7_with_concept = pd.merge(df_gt7, concept_df, on="code", how="inner")
    print(f"提示：涨跌幅>9%且匹配到概念的股票数 - {len(df_gt9_with_concept)}；>7% - {len(df_gt7_with_concept)}")

    # 6. 核心步骤3：按概念统计达标家数，并按家数降序排序（核心需求）
    # 统计涨幅>9%的概念家数并排序
    concept_gt9_count = df_gt9_with_concept.groupby("所属概念").agg(
        涨幅_9_percent_家数=("code", "nunique"),  # nunique确保单股票多概念不重复统计
        板块内达标股票列表=("code", lambda x: ",".join(x.unique()))  # 可选：展示达标股票代码
    ).reset_index()
    concept_gt9_rank = concept_gt9_count.sort_values("涨幅_9_percent_家数", ascending=False).reset_index(drop=True)
    concept_gt9_rank["排名"] = concept_gt9_rank.index + 1  # 新增排名列

    # 统计涨幅>7%的概念家数并排序
    concept_gt7_count = df_gt7_with_concept.groupby("所属概念").agg(
        涨幅_7_percent_家数=("code", "nunique"),
        板块内达标股票列表=("code", lambda x: ",".join(x.unique()))
    ).reset_index()
    concept_gt7_rank = concept_gt7_count.sort_values("涨幅_7_percent_家数", ascending=False).reset_index(drop=True)
    concept_gt7_rank["排名"] = concept_gt7_rank.index + 1  # 新增排名列

    # 7. 获取所有达标股票的所属概念集合
    top_concepts = set(
        df_gt9_with_concept["所属概念"].dropna().tolist() +
        df_gt9_with_concept["所属概念"].dropna().tolist()
    )

    return concept_gt9_rank, concept_gt7_rank, top_concepts


# ===================== 原有函数：获取概念内竞价成交额排名（兼容保留）=====================
def get_top_auction_stocks(top_concepts, lookback_days=5, data_path="./data/raw"):
    """获取指定概念板块近N日竞价成交额/增量前15名股票（逻辑无修改，兼容原有调用）"""

    def get_trade_dates(lookback):
        trade_dates = []
        current_date = datetime.now().date()
        while len(trade_dates) < lookback:
            if current_date.weekday() < 5:
                trade_dates.append(current_date)
            current_date -= timedelta(days=1)
        return trade_dates[::-1]

    trade_dates = get_trade_dates(lookback_days)
    if not trade_dates:
        print("警告：未获取到有效交易日")
        return pd.DataFrame(), pd.DataFrame()

    concept_df = safe_read_csv(os.path.join("./metadata", "所属概念.csv"))
    concept_df = drop_duplicate_columns(concept_df)
    if concept_df.empty or not all(col in concept_df.columns for col in ["股票代码", "所属概念"]):
        print("警告：概念映射表异常")
        return pd.DataFrame(), pd.DataFrame()
    concept_df = concept_df.rename(columns={"股票代码": "code"})[["code", "所属概念"]].copy()
    concept_df["code"] = concept_df["code"].astype(str)

    daily_top_amount = []
    daily_top_diff = []
    for i, date in enumerate(trade_dates):
        date_str = date.strftime('%Y-%m-%d')
        file_path = os.path.join(data_path, f"{date_str}_竞价行情.csv")
        df = safe_read_csv(file_path)
        if df.empty or "code" not in df.columns or "auction_amount" not in df.columns:
            continue
        df = drop_duplicate_columns(df)
        df["code"] = df["code"].astype(str)
        df = pd.merge(df, concept_df, on="code", how="inner")
        df = df[df["所属概念"].isin(top_concepts)]
        if df.empty:
            continue

        # 竞价成交额前15名
        daily_amount = df.sort_values("auction_amount", ascending=False).head(15).copy()
        daily_amount["日期"] = date
        daily_amount["排名类型"] = "竞价成交额"
        daily_top_amount.append(daily_amount)

        # 竞价成交额增量前15名（仅从第2天开始计算）
        if i > 0:
            prev_file = os.path.join(data_path, f"{trade_dates[i - 1].strftime('%Y-%m-%d')}_竞价行情.csv")
            prev_df = safe_read_csv(prev_file)
            if not prev_df.empty and "code" in prev_df.columns and "auction_amount" in prev_df.columns:
                prev_df["code"] = prev_df["code"].astype(str)
                merge_df = pd.merge(df, prev_df[["code", "auction_amount"]], on="code",
                                    suffixes=("_today", "_yesterday"))
                merge_df["amount_diff"] = merge_df["auction_amount_today"] - merge_df["auction_amount_yesterday"]
                daily_diff = merge_df.sort_values("amount_diff", ascending=False).head(15).copy()
                daily_diff["日期"] = date
                daily_diff["排名类型"] = "竞价成交额增量"
                daily_top_diff.append(daily_diff)

    # 合并结果并去重列
    all_top_amount = pd.concat(daily_top_amount, ignore_index=True) if daily_top_amount else pd.DataFrame()
    all_top_diff = pd.concat(daily_top_diff, ignore_index=True) if daily_top_diff else pd.DataFrame()
    all_top_amount = drop_duplicate_columns(all_top_amount)
    all_top_diff = drop_duplicate_columns(all_top_diff)

    return all_top_amount, all_top_diff


# ===================== 测试代码：直接运行查看结果 ======================
if __name__ == "__main__":
    # 测试目标日期（可替换为指定date(YYYY, MM, DD)）
    test_date = datetime.now().date()
    # 计算概念强度（核心：按涨幅达标家数排序）
    rank_gt9, rank_gt7, top_concepts = calculate_concept_strength(test_date)

    # 打印涨幅>9%家数排名（核心结果）
    print("=" * 50)
    print("涨幅>9%的概念板块排名（按家数从多到少）")
    print("=" * 50)
    if not rank_gt9.empty:
        print(rank_gt9[["排名", "所属概念", "涨幅_9_percent_家数", "板块内达标股票列表"]].fillna("-"))
    else:
        print("无符合条件的概念板块")

    # 打印涨幅>7%家数排名（核心结果）
    print("\n" + "=" * 50)
    print("涨幅>7%的概念板块排名（按家数从多到少）")
    print("=" * 50)
    if not rank_gt7.empty:
        print(rank_gt7[["排名", "所属概念", "涨幅_7_percent_家数", "板块内达标股票列表"]].fillna("-"))
    else:
        print("无符合条件的概念板块")

    # 可选：获取概念内竞价成交额排名
    if top_concepts:
        top_amount, top_diff = get_top_auction_stocks(top_concepts)
        print(f"\n提示：从{len(top_concepts)}个达标概念中，筛选出近5日竞价成交额排名{len(top_amount)}条")