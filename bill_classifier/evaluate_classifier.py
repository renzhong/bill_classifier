import logging
import configparser
import argparse

from feishu import FeishuSheetAPI
from feishu_auth import FeishuAuthError, get_valid_user_access_token
from classifier_gpt import GPTClassifier
from bill_config import BillConfig, ModelConfig


class ClassifierEvaluator:
    def __init__(self, user_access_token, sheet_token, model_config: ModelConfig):
        self.feishu_api = FeishuSheetAPI(user_access_token, sheet_token)
        self.classifier = GPTClassifier(model_config)
        self.correct_count = 0
        self.error_count = 0
        self.error_items = []

    def evaluate(self, sheet_range):
        """
        评测分类模型
        :param sheet_range: 要评测的数据范围
        :return: (正确数, 错误数, 正确率, 错误项列表)
        """
        # 1. 获取测试数据
        success, test_data_list = self.feishu_api.GetClassificationTestData(sheet_range)
        if not success:
            logging.error("获取测试数据失败")
            return 0, 0, 0.0, []

        # 2. 对每条数据进行分类并对比
        for item in test_data_list:
            predicted_category = self.classifier.call(item['item_name'], item['payee'], item['amount'], item['bill_time'])
            actual_category = item['category']

            if predicted_category == actual_category:
                self.correct_count += 1
            else:
                self.error_count += 1
                self.error_items.append({
                    'item_name': item['item_name'],
                    'payee': item['payee'],
                    'actual_category': actual_category,
                    'predicted_category': predicted_category
                })

        # 3. 计算正确率
        total = self.correct_count + self.error_count
        accuracy = self.correct_count / total if total > 0 else 0.0

        return self.correct_count, self.error_count, accuracy, self.error_items


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('--config_file', help='配置文件路径')
    args = parser.parse_args()
    config = configparser.ConfigParser()
    config.read(args.config_file)

    bill_config = BillConfig(config)
    model_config = bill_config.gpt_config.current_model

    try:
        user_access_token = get_valid_user_access_token(config, args.config_file)
    except FeishuAuthError as err:
        logging.error(str(err))
        return
    sheet_token = 'OxRdst6mhhclLGtOYTncmRenncb'

    if not user_access_token:
        logging.error("缺少飞书 user_access_token")
        return

    evaluator = ClassifierEvaluator(user_access_token, sheet_token, model_config)

    correct, error, accuracy, error_items = evaluator.evaluate('ad3acc')

    print("\n评测结果:")
    print(f"使用模型: {model_config.name} ({model_config.model_name} @ {model_config.base_url})")
    print(f"正确数: {correct}")
    print(f"错误数: {error}")
    print(f"正确率: {accuracy:.2%}")
    print("\n分类错误的数据:")
    for item in error_items:
        print(f"商品: {item['item_name']}")
        print(f"商家: {item['payee']}")
        print(f"实际分类: {item['actual_category']}")
        print(f"预测分类: {item['predicted_category']}")
        print("-" * 50)


if __name__ == "__main__":
    main()
