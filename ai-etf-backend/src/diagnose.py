# -*- coding: utf-8 -*-
"""
诊断脚本：检查 API 连接和配置是否正确
运行方式：python -m src.diagnose
"""
import os
import sys
from dotenv import load_dotenv

def check_environment():
    """检查环境变量配置"""
    print("=" * 60)
    print("环境变量检查")
    print("=" * 60)
    
    load_dotenv()
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY 未设置")
        return False
    
    if api_key.startswith("sk-"):
        print(f"OPENAI_API_KEY: {api_key[:10]}...{api_key[-5:]}")
    else:
        print(f"OPENAI_API_KEY 格式可能不正确: {api_key[:20]}...")
    
    model = os.getenv("MODEL_NAME", "gpt-4o-mini")
    print(f"MODEL_NAME: {model}")
    
    timeout = os.getenv("TIMEOUT_SECONDS", "120")
    print(f"TIMEOUT_SECONDS: {timeout}")
    
    retries = os.getenv("MAX_RETRIES", "5")
    print(f"MAX_RETRIES: {retries}")
    
    fallback = os.getenv("FALLBACK_MODELS", "gpt-3.5-turbo,gpt-4")
    print(f"FALLBACK_MODELS: {fallback}")
    
    base_url = os.getenv("BASE_URL")
    if base_url:
        print(f"BASE_URL: {base_url}")
    else:
        print("BASE_URL: 未设置（使用官方 OpenAI API）")
    
    return True


def check_openai_library():
    """检查 OpenAI 库是否安装"""
    print("\n" + "=" * 60)
    print("依赖库检查")
    print("=" * 60)
    
    try:
        import openai
        print(f"openai: {openai.__version__}")
    except ImportError:
        print("openai 库未安装，请运行: pip install openai")
        return False
    
    try:
        import pandas
        print(f"pandas: {pandas.__version__}")
    except ImportError:
        print("pandas 库未安装")
        return False
    
    try:
        import dotenv
        print("python-dotenv: 已安装")
    except ImportError:
        print("python-dotenv 库未安装")
        return False
    
    return True


def test_api_connection():
    """测试 API 连接"""
    print("\n" + "=" * 60)
    print("API 连接测试")
    print("=" * 60)
    
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("跳过 API 测试（API 密钥未配置）")
        return False
    
    try:
        from openai import OpenAI
        
        base_url = os.getenv("BASE_URL")
        timeout = float(os.getenv("TIMEOUT_SECONDS", "120"))
        
        client_kwargs = {
            "api_key": api_key,
            "timeout": timeout,
            "max_retries": 1
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        
        client = OpenAI(**client_kwargs)
        
        print("发送测试请求到 OpenAI API...")
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say OK only."}
            ],
            temperature=0.3,
            timeout=timeout,
        )
        
        result = resp.choices[0].message.content
        print("API 连接成功!")
        print(f"模型响应: {result}")
        print(f"使用 tokens: {resp.usage.total_tokens}")
        return True
        
    except Exception as e:
        print(f"API 连接失败: {e}")
        print("建议:")
        print("1. 检查 API 密钥是否正确")
        print("2. 检查网络连接")
        print("3. 检查账户余额")
        print("4. 如果使用代理，检查 BASE_URL 是否正确")
        return False


def check_database():
    """检查数据库"""
    print("\n" + "=" * 60)
    print("数据库检查")
    print("=" * 60)
    
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "etf_data.db")
    if os.path.exists(db_path):
        size = os.path.getsize(db_path) / 1024 / 1024
        print(f"ETF 数据库存在: {db_path}")
        print(f"大小: {size:.2f} MB")
    else:
        print(f"ETF 数据库不存在: {db_path}")
        print("首次运行时会自动创建")
    
    trade_db = os.path.join(os.path.dirname(__file__), "..", "data", "trade_history.db")
    if os.path.exists(trade_db):
        size = os.path.getsize(trade_db) / 1024 / 1024
        print(f"交易历史数据库存在: {trade_db}")
        print(f"大小: {size:.2f} MB")
    else:
        print(f"交易历史数据库不存在: {trade_db}")
        print("首次运行时会自动创建")


def main():
    """主诊断流程"""
    print("\n")
    print("AI ETF Trader 诊断工具")
    print("=" * 60)
    
    results = []
    
    # 检查环境变量
    results.append(("环境变量", check_environment()))
    
    # 检查依赖库
    results.append(("依赖库", check_openai_library()))
    
    # 检查数据库
    check_database()
    
    # 测试 API 连接
    results.append(("API 连接", test_api_connection()))
    
    # 总结
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)
    
    all_passed = True
    for name, result in results:
        status = "通过" if result else "失败"
        print(f"{name}: {status}")
        if not result:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("所有检查通过！系统已准备就绪。")
        print("运行: python -m src.main")
    else:
        print("存在问题需要解决，请查看上面的错误信息。")
        print("详见: CONFIG_GUIDE.md")
    print("=" * 60 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())


