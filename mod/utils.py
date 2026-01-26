import sys
import pandas as pd
from pathlib import Path
from .config import COLUMN_MAPPING

class Logger:
    """同时输出到控制台和文件的日志器"""
    def __init__(self, filename: str, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self.terminal = sys.stdout
        self.log = open(path / filename, "w", encoding='utf-8')

    def write(self, message: str):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()
        sys.stdout = self.terminal


def safe_read_csv(file_path: Path) -> pd.DataFrame:
    """安全读取CSV，支持gbk和utf-8-sig编码"""
    if not file_path.exists():
        return pd.DataFrame()
    for encoding in ['gbk', 'utf-8-sig']:
        try:
            return pd.read_csv(file_path, encoding=encoding  , dtype=str)
        except Exception:
            continue
    print(f"⚠️ 无法读取文件（编码失败）：{file_path}")
    return pd.DataFrame()


def standardize_code(code: str) -> str:
    """统一股票代码格式：sh/sz/bj + 6位数字"""
    digits = ''.join(filter(str.isdigit, str(code)))
    if not digits:
        return ''
    digits = digits.zfill(6)
    if digits.startswith('6'):
        return f"sh{digits}"
    if digits[0] in '489':
        return f"bj{digits}"
    return f"sz{digits}"


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """统一清洗：列名映射、代码标准化、去除重复列"""
    if df.empty:
        return df

    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns=COLUMN_MAPPING)

    # 去除重复列
    df = df.loc[:, ~df.columns.duplicated()]

    # 标准化股票代码
    if '股票代码' in df.columns:
        df['股票代码'] = df['股票代码'].apply(standardize_code)

    return df

def print_md_table(df: pd.DataFrame, title: str, subtitle: str = ""):
    """打印Markdown格式的表格"""
    if df.empty:
        return
    print(f"\n### {title}")
    if subtitle:
        print(f"*{subtitle}*")
    print(df.to_markdown(index=False))
    print("\n")


# modules/utils.py
import streamlit as st
import requests
import os

def check_password():
    """检测访问环境：本机/局域网免密，外网需密码"""
    # 1. 获取访问者 IP
    headers = st.context.headers
    client_ip = headers.get("x-forwarded-for", "127.0.0.1").split(",")[0]

    # 2. 白名单逻辑
    is_local = (
        client_ip == "127.0.0.1" or 
        client_ip == "localhost" or 
        client_ip.startswith("192.168.") or 
        client_ip.startswith("172.") or
        client_ip.startswith("10.")
    )

    if is_local:
        return True

    # 3. 密码校验逻辑
    def password_entered():
        if st.session_state["password"] == st.secrets.get("ACCESS_PASSWORD", "888888oooo42"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🛡️ 远程访问受限，请输入密码", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("❌ 密码错误，请重新输入", type="password", on_change=password_entered, key="password")
        return False
    else:
        return True

def trigger_github_action():
    """通过 GitHub API 远程触发数据抓取任务"""
    token = st.secrets.get("GITHUB_TOKEN")
    owner = st.secrets.get("GITHUB_USER")
    repo = st.secrets.get("GITHUB_REPO")
    
    if not all([token, owner, repo]):
        st.error("未配置 GitHub Secrets")
        return False
    
    url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"event_type": "manual_fetch_trigger"}
    
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 204:
            st.success("🚀 指令已发出！机器人已开始抓取。")
            return True
        else:
            st.error(f"❌ 触发失败：{response.status_code}")
            return False
    except Exception as e:
        st.error(f"🌐 连接失败: {e}")
        return False

def run_data_download_script():
    try:
        # 获取当前文件的绝对路径，确保定位到 main.py(本地运行用这个函数)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(current_dir, "main.py")
        
        # 【核心修改】：使用 sys.executable 而不是 "python"
        # sys.executable 会直接指向当前已经装好 pandas 的那个 Python 解释器
        result = subprocess.run(
            [sys.executable, script_path], 
            capture_output=True, 
            text=True,
            encoding='utf-8'
        )
        
        if result.returncode == 0:
            return True, "数据更新成功！"
        else:
            # 这里的 stderr 会捕捉到 main.py 内部的报错
            return False, f"更新失败: {result.stderr}"
    except Exception as e:
        return False, f"程序异常: {str(e)}"

