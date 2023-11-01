import os
import openai
import logging

class GPTClassifier:
    prompt_template = """
你是一个在北京生活多年的家庭主妇,擅长对账单进行分类,分类的类别包括:{},那么账单:'{}',来自'{}',应该属于哪类?如果判断不了回答'unknown',请只回答类别名称
    """

    class_list = "'餐饮','日常开支','服装鞋帽','护肤品','水电物业','医疗'"
    token_count = 0


    def __init__(self, class_list = ""):
        if len(class_list) > 0:
            self.class_list = class_list
        self.token_count = 0

    def call(self, item_name, payee):
        prompt = self.prompt_template.format(self.class_list, item_name, payee)
        logging.debug("promt:{}".format(prompt))
        # TODO: 修改模型
        response = openai.Completion.create(
            model="gpt-3.5-turbo-instruct",
            prompt=prompt,
            temperature=0,
            # max_tokens=2000,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0
        )

        # logging.debug("chat response:{}".format(response))
        self.token_count = self.token_count + response["usage"]["total_tokens"]

        finish_reason = response["choices"][0]["finish_reason"]
        text = response["choices"][0]["text"]
        if finish_reason != "stop":
            logging.error("使用 gpt 推理分类失败:", finish_reason)
            return ""
        text = text.strip("\n")
        return text

    def get_token_count(self):
        return self.token_count

if __name__ == '__main__':
    openai.api_key = os.getenv("OPENAI_API_KEY")

    from category import expense_category_mapping  # noqa: F403
    classifier = GPTClassifier()
    text = classifier.call("7-ELEVEn北京黄寺大街西侧店消费", "7-11(SEB)")
    print(text)
    if text not in expense_category_mapping:
        print("text not in expense_category_mapping")
    else:
        print("text in expense_category_mapping")
