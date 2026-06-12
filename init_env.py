"""一键初始化脚本：复制 .env.example 并引导用户配置"""
import os
import sys

def main():
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            with open(".env.example", "r", encoding="utf-8") as f:
                content = f.read()
            with open(".env", "w", encoding="utf-8") as f:
                f.write(content)
            print("✅ 已创建 .env 文件，请编辑配置你的 API Key")
        else:
            print("❌ 未找到 .env.example 文件")
            sys.exit(1)
    else:
        print("✅ .env 文件已存在")

    print("\n" + "="*50)
    print("A股情报系统 初始化完成！")
    print("="*50)
    print("\n下一步：")
    print("1. 编辑 .env 文件，填入配置信息")
    print("2. 运行 pip install -r requirements.txt")
    print("3. 运行 python main.py init 检查配置")
    print("4. 运行 python main.py all 测试全流程")
    print("\n推荐 AI 配置（零成本）：")
    print("  - Google Gemini: https://aistudio.google.com/app/apikey")
    print("\n飞书 Webhook 配置：")
    print("  飞书群 → 设置 → 群机器人 → 添加机器人 → 复制 Webhook URL")
    print("="*50)

if __name__ == "__main__":
    main()
