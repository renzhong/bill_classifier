from openai import OpenAI
import json

from bill_config import ModelConfig


class GPTClassifier:
    # 系统提示词：定义角色、任务和输出格式
    system_template = """
    角色：你是一位在北京生活多年的家庭主妇，对日常消费和账单分类有丰富的经验。

    任务：对账单进行分类，需要你：
    1. 仔细分析账单的所有信息（名称、支付方、金额、时间等）
    2. 结合你的生活经验，判断最合适的分类
    3. 如果信息不足或无法确定，返回 'unknown'

    输出要求：
    1. 使用 JSON 格式返回结果
    2. 只返回 category 字段
    3. category 的值必须是以下类别之一：{}

    注意事项：
    1. 保持客观，不要过度推理
    2. 如果信息模糊，宁可返回 'unknown' 也不要随意猜测
    3. 考虑账单的完整上下文
    """

    # 用户提示词：提供具体的账单信息
    user_template = """
    请对以下账单进行分类：

    账单信息：
    - 名称：{item_name}
    - 支付方：{payee}
    - 金额：{amount}元
    - 时间：{timestamp}

    请根据以上信息，给出最合适的分类。
    """

    class_list = "'餐饮','日常开支','服装鞋帽','护肤品','水电物业','医疗','育儿','交通'"
    class_index = {
        "dining": "餐饮",
        "daily expenses": "日常开支",
        "clothing and footwear": "服装鞋帽",
        "skincare products": "护肤品",
        "utilities and properties": "水电物业",
        "medical": "医疗",
        "unknown": "unknown"
    }

    def __init__(self, model_config: ModelConfig, class_list: str = ""):
        if len(class_list) > 0:
            self.class_list = class_list
        self.token_count = 0
        self.model_config = model_config
        self.client = OpenAI(
            api_key=model_config.api_key,
            base_url=model_config.base_url,
        )

    def call(self, item_name, payee, amount, timestamp):
        system_content = self.system_template.format(self.class_list)
        user_content = self.user_template.format(
            item_name=item_name,
            payee=payee,
            amount=amount,
            timestamp=timestamp
        )

        response = self.client.chat.completions.create(
            model=self.model_config.model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ]
        )

        self.token_count += response.usage.total_tokens
        content = json.loads(response.choices[0].message.content)
        return content["category"]

    def get_token_count(self):
        return self.token_count


if __name__ == '__main__':
    import argparse
    import configparser

    from bill_config import BillConfig
    from category import expense_category_mapping  # noqa: F403

    parser = argparse.ArgumentParser()
    parser.add_argument('--config_file', default='config/config.ini')
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config_file)
    bill_config = BillConfig(config)

    classifier = GPTClassifier(bill_config.gpt_config.current_model)

    text = classifier.call("7-ELEVEn北京黄寺大街西侧店消费", "7-11(SEB)", 35, "2024-03-20 14:30")
    print(text)
    if text not in expense_category_mapping:
        print("text not in expense_category_mapping")
    else:
        print("text in expense_category_mapping")
