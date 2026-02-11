"""
AI 调用公共模块
支持智谱 AI 和其他 LLM 提供商，支持联网功能
"""

import os
import json
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pathlib import Path
from litellm import completion, acompletion
from litellm.exceptions import APIError, RateLimitError


class AIClient:
    """AI 客户端基类"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "zhipu/glm-4-flash",
        **kwargs
    ):
        """
        初始化 AI 客户端

        Args:
            api_key: API 密钥
            base_url: API 基础 URL
            model: 模型名称
            **kwargs: 其他参数
        """
        self.api_key = api_key or os.getenv("ZHIPUAI_API_KEY")
        self.base_url = base_url
        self.model = model
        self.extra_params = kwargs

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送聊天请求

        Args:
            messages: 消息列表，格式: [{"role": "user", "content": "..."}]
            temperature: 温度参数 (0-1)
            max_tokens: 最大 token 数
            tools: 工具列表（用于联网等）
            **kwargs: 其他参数

        Returns:
            包含响应内容的字典
        """
        try:
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                **self.extra_params,
                **kwargs
            }

            if max_tokens:
                params["max_tokens"] = max_tokens

            if tools:
                params["tools"] = tools

            if self.api_key:
                params["api_key"] = self.api_key

            if self.base_url:
                params["api_base"] = self.base_url

            response = completion(**params)
            return self._parse_response(response)

        except RateLimitError as e:
            return {
                "success": False,
                "error": "rate_limit_exceeded",
                "message": str(e)
            }
        except APIError as e:
            return {
                "success": False,
                "error": "api_error",
                "message": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "error": "unknown_error",
                "message": str(e)
            }

    def _parse_response(self, response) -> Dict[str, Any]:
        """
        解析响应

        Args:
            response: litellm 响应对象

        Returns:
            解析后的字典
        """
        try:
            choices = response.get("choices", [])
            if not choices:
                return {
                    "success": False,
                    "error": "no_response",
                    "message": "No response from AI"
                }

            first_choice = choices[0]
            message = first_choice.get("message", {})

            result = {
                "success": True,
                "content": message.get("content", ""),
                "role": message.get("role", "assistant"),
                "finish_reason": first_choice.get("finish_reason"),
                "usage": response.get("usage", {}),
                "model": response.get("model", self.model),
                "id": response.get("id"),
            }

            # 如果有工具调用，添加到结果中
            if "tool_calls" in message:
                result["tool_calls"] = message["tool_calls"]

            return result

        except Exception as e:
            return {
                "success": False,
                "error": "parse_error",
                "message": str(e)
            }

    async def achat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        异步聊天请求

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            包含响应内容的字典
        """
        try:
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                **self.extra_params,
                **kwargs
            }

            if max_tokens:
                params["max_tokens"] = max_tokens

            if self.api_key:
                params["api_key"] = self.api_key

            if self.base_url:
                params["api_base"] = self.base_url

            response = await acompletion(**params)
            return self._parse_response(response)

        except Exception as e:
            return {
                "success": False,
                "error": "async_error",
                "message": str(e)
            }


class AIHelper:
    """
    AI 助手类 - 提供便捷的静态方法
    专为智谱 AI 优化，支持联网功能
    """

    # 默认模型配置
    DEFAULT_MODELS = {
        "zhipu": {
            "flash": "zhipu/glm-4-flash",      # 免费快速模型
            "plus": "zhipu/glm-4-plus",        # 增强模型
            "air": "zhipu/glm-4-air",          # 轻量级模型
            "search": "zhipu/glm-4-flash",     # 带联网搜索
        }
    }

    # 联网工具定义（智谱 AI web_search）
    WEB_SEARCH_TOOL = {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网信息，获取最新数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询关键词"
                    }
                },
                "required": ["query"]
            }
        }
    }

    @staticmethod
    def get_client(
        model: str = "zhipu/glm-4-flash",
        api_key: Optional[str] = None
    ) -> AIClient:
        """
        获取 AI 客户端实例

        Args:
            model: 模型名称
            api_key: API 密钥（可选，默认从环境变量读取）

        Returns:
            AIClient 实例
        """
        return AIClient(model=model, api_key=api_key)

    @staticmethod
    def chat(
        prompt: str,
        model: str = "zhipu/glm-4-flash",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        enable_web_search: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        简单的文本对话

        Args:
            prompt: 用户输入
            model: 模型名称
            system_prompt: 系统提示词
            temperature: 温度参数
            api_key: API 密钥
            enable_web_search: 是否启用联网搜索
            **kwargs: 其他参数

        Returns:
            响应结果字典
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        client = AIClient(model=model, api_key=api_key)

        # 如果启用联网搜索
        tools = [AIHelper.WEB_SEARCH_TOOL] if enable_web_search else None

        return client.chat(
            messages=messages,
            temperature=temperature,
            tools=tools,
            **kwargs
        )

    @staticmethod
    def chat_with_web_search(
        prompt: str,
        model: str = "zhipu/glm-4-flash",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        带联网搜索的对话

        Args:
            prompt: 用户输入
            model: 模型名称
            system_prompt: 系统提示词
            temperature: 温度参数
            api_key: API 密钥
            **kwargs: 其他参数

        Returns:
            响应结果字典
        """
        return AIHelper.chat(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            api_key=api_key,
            enable_web_search=True,
            **kwargs
        )

    @staticmethod
    def chat_conversation(
        messages: List[Dict[str, str]],
        model: str = "zhipu/glm-4-flash",
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        多轮对话

        Args:
            messages: 消息历史
            model: 模型名称
            temperature: 温度参数
            api_key: API 密钥
            **kwargs: 其他参数

        Returns:
            响应结果字典
        """
        client = AIClient(model=model, api_key=api_key)
        return client.chat(messages=messages, temperature=temperature, **kwargs)

    @staticmethod
    def extract_json(response: str) -> Optional[Dict]:
        """
        从响应中提取 JSON

        Args:
            response: AI 响应文本

        Returns:
            解析后的 JSON 字典，失败返回 None
        """
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取 JSON 代码块
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

            # 尝试提取大括号内容
            brace_match = re.search(r'\{.*\}', response, re.DOTALL)
            if brace_match:
                try:
                    return json.loads(brace_match.group(0))
                except json.JSONDecodeError:
                    pass

            return None

    @staticmethod
    def save_conversation(
        messages: List[Dict[str, str]],
        response: Dict[str, Any],
        filepath: Optional[str] = None
    ):
        """
        保存对话记录到文件

        Args:
            messages: 消息历史
            response: AI 响应
            filepath: 保存路径（可选）
        """
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"conversation_{timestamp}.json"

        data = {
            "timestamp": datetime.now().isoformat(),
            "messages": messages,
            "response": response
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"对话记录已保存到: {filepath}")


# 便捷函数
def chat(prompt: str, **kwargs) -> Dict[str, Any]:
    """
    快速对话函数

    Args:
        prompt: 用户输入
        **kwargs: 其他参数

    Returns:
        AI 响应
    """
    return AIHelper.chat(prompt, **kwargs)


def chat_with_search(prompt: str, **kwargs) -> Dict[str, Any]:
    """
    带联网搜索的快速对话

    Args:
        prompt: 用户输入
        **kwargs: 其他参数

    Returns:
        AI 响应
    """
    return AIHelper.chat_with_web_search(prompt, **kwargs)
