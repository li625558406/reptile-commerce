"""
AI 调用示例脚本
演示如何使用公共 AI 模块
"""

import os
from dotenv import load_dotenv
from utils.ai_helper import AIHelper, chat, chat_with_search

# 加载环境变量
load_dotenv()


def example_1_simple_chat():
    """示例 1: 简单对话"""
    print("\n" + "=" * 60)
    print("示例 1: 简单对话")
    print("=" * 60)

    response = chat(
        prompt="请用一句话介绍 Python 编程语言",
        model="zhipu/glm-4-flash"
    )

    if response.get("success"):
        print(f"AI 回复: {response['content']}")
        print(f"使用 Token: {response.get('usage', {})}")
    else:
        print(f"请求失败: {response.get('message')}")


def example_2_chat_with_system():
    """示例 2: 带系统提示词的对话"""
    print("\n" + "=" * 60)
    print("示例 2: 带系统提示词的对话")
    print("=" * 60)

    response = AIHelper.chat(
        prompt="帮我分析一下空气净化器的关键指标",
        system_prompt="你是一个专业的家电分析师，擅长分析产品参数和性能",
        model="zhipu/glm-4-flash"
    )

    if response.get("success"):
        print(f"AI 回复:\n{response['content']}")
    else:
        print(f"请求失败: {response.get('message')}")


def example_3_web_search():
    """示例 3: 带联网搜索的对话"""
    print("\n" + "=" * 60)
    print("示例 3: 带联网搜索的对话")
    print("=" * 60)

    response = AIHelper.chat_with_web_search(
        prompt="2024 年最好的空气净化器品牌有哪些？",
        model="zhipu/glm-4-flash"
    )

    if response.get("success"):
        print(f"AI 回复:\n{response['content']}")

        # 如果有工具调用结果
        if response.get("tool_calls"):
            print(f"\n使用了联网搜索工具")
    else:
        print(f"请求失败: {response.get('message')}")


def example_4_conversation():
    """示例 4: 多轮对话"""
    print("\n" + "=" * 60)
    print("示例 4: 多轮对话")
    print("=" * 60)

    messages = [
        {"role": "system", "content": "你是一个专业的产品分析师"},
        {"role": "user", "content": "什么是 CADR 值？"},
    ]

    # 第一轮
    response1 = AIHelper.chat_conversation(messages)
    if response1.get("success"):
        print(f"用户: 什么是 CADR 值？")
        print(f"AI: {response1['content']}\n")

        # 添加 AI 回复到消息历史
        messages.append({
            "role": "assistant",
            "content": response1['content']
        })

        # 第二轮追问
        messages.append({
            "role": "user",
            "content": "那么针对 50 平米的房间，建议多少 CADR 值？"
        })

        response2 = AIHelper.chat_conversation(messages)
        if response2.get("success"):
            print(f"用户: 那么针对 50 平米的房间，建议多少 CADR 值？")
            print(f"AI: {response2['content']}")
        else:
            print(f"第二轮失败: {response2.get('message')}")
    else:
        print(f"第一轮失败: {response1.get('message')}")


def example_5_use_other_script():
    """示例 5: 在其他脚本中使用"""
    print("\n" + "=" * 60)
    print("示例 5: 在其他脚本中使用")
    print("=" * 60)

    # 模拟在其他脚本中调用
    from utils.ai_helper import AIHelper

    # 获取产品描述
    product_name = "某品牌空气净化器"
    prompt = f"请为 {product_name} 写一段吸引人的产品描述，突出净化效果"

    response = AIHelper.chat(
        prompt=prompt,
        system_prompt="你是一个专业的产品文案撰写专家",
        temperature=0.9,  # 提高创造性
    )

    if response.get("success"):
        print(f"产品描述:\n{response['content']}")
    else:
        print(f"请求失败: {response.get('message')}")


def example_6_check_api_key():
    """示例 0: 检查 API Key 配置"""
    print("\n" + "=" * 60)
    print("检查环境配置")
    print("=" * 60)

    api_key = os.getenv("ZHIPUAI_API_KEY")

    if not api_key or api_key == "your_zhipuai_api_key_here":
        print("❌ 未配置 ZHIPUAI_API_KEY")
        print("\n请按以下步骤配置:")
        print("1. 复制 .env.example 为 .env")
        print("2. 在 .env 文件中填入你的智谱 AI API Key")
        print("3. API Key 获取地址: https://open.bigmodel.cn/")
        return False

    print("✅ API Key 已配置")
    return True


def main():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("AI 公共模块使用示例")
    print("=" * 60)

    # 检查配置
    if not example_6_check_api_key():
        return

    try:
        # 运行示例
        example_1_simple_chat()
        example_2_chat_with_system()
        example_3_web_search()
        example_4_conversation()
        example_5_use_other_script()

        print("\n" + "=" * 60)
        print("所有示例运行完成!")
        print("=" * 60)

    except Exception as e:
        print(f"\n运行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
