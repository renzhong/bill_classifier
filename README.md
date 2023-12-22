# 简介
本项目可以用于统计自己每个月的收入与支出，简单来说，本项目可以通过 python 处理微信支付宝账单，然后借助在线文档 API 将处理结果上传到在线文档，实现文档的三端展示，最后使用了一些 excel 技巧，可以方便的逐级汇总信息，最后产出账单信息。

# 表格特点
- 账单明细 YYYYMM: 汇总每个月的单笔账单，账单的数据来源是微信和支付宝的账单。
- 月度明细: 按照分类统计每个月的花销
- 股票基金: 记录每个月投资相关的支出与收入
- 结余表: 汇总当前的资金情况，计算当月余额
- 个人记账本: 年汇总每个月的收入与支出，每个月的收入支出一目了然

# 脚本逻辑
1. 读入微信和支付宝的账单(账单需要由用户自己去微信 or 支付宝下载)
2. 解析账单
3. 处理退款账单，分为三类：
    - 退款部分金额的账单会更新扣除退款的金额
    - 全部退款的账单会从最终结果中剔除
    - 上月账单的退款账单会单独记录
4. 自动识别账单分类，目前主要采用字典的形式识别
5. 识别买菜账单：分类字典中有部分易识别的买菜订单，当可识别的订单前后一小时内有无法识别的账单时，这些无法识别的账单全部不标记为买菜账单
6. 通过在线文档 API 新建 '账单明细 YYYYMM'，将结果上传。

# 脚本使用
1. 微信 or 支付宝的账单导出方式，参考视频: https://www.bilibili.com/video/BV1or4y1J7ke/
2. 在 main.py 中修改账单的路径
3. 获取在线文档模板
    1. 在线文档模板: https://vgk5e2s4w1.feishu.cn/sheets/shtcnn77JLFDh0ZEcesIMYTb8Nf
    2. 点击右上角: '使用该模板'，在自己的账户中新建文档
4. 在 main.py 中填入调用 openapi 需要的信息
    - user_access_token: 点击链接: https://open.feishu.cn/api-explorer/cli_a4d9e0b5c9bd100b
    - sheet_token: 文档链接中的类似 'shtcnn77JLFDh0ZEcesIMYTb8Nf' 字符串

# 最终文档格式
## 账单明细 YYYYMM
账单明细 sheet 用来汇总每个月的单笔账单，账单的数据来源是微信和支付宝的账单，python 脚本会读取微信支付宝账单，然后自动识别账单的分类，无法识别的账单用户可以自行标记分类。

## 月度明细
月度明细 sheet 用来按照分类统计每个月的花销，每个分类的数据由 python 脚本来更新，数据来源是'账单明细 YYYYMM'

## 股票基金
股票基金 sheet 用来记录每个月投资相关的支出与收入

## 结余表
结余表 sheet 用来汇总当前的资金情况，包括各个银行卡中的余额，本月需要支付的账单，包括房贷、车贷、信用卡、花呗等项。
- '信用卡' + '未出账单': 我们通过 '信用卡' + '未出账单' - 上月'未出账单' 得出当月的信用卡待还
- '已扣贷款': 由于每笔账单的还款日期不一样，每月产生表格时，可能某些账单已经支付过，特意留出'已扣贷款'行来记录已还贷款，在'待还'行的计算中会把'已扣贷款'行减除。
- '股票现状': '股票现状'行的数据自动同步 '股票基金' sheet 中的当月数据
- '结余': '结余'的数据由 '总现金' - '待还' + '股票基金' 得出。

## 个人记账本
个人记账本 sheet 用来按年汇总每个月的收入与支出

- 每月收入: 每月收入分为多行，对应家庭每个人的工资、额外收入。
- 股票收益: 股票收益是指每个月股票的盈亏情况，我们其实并不关心短期的股票涨跌，但我们关心每个月的支出情况，如果忽略股票收益，每个月的支出情况可能会有误差。
- 房贷/车贷: 每个月的固定支出
- 日常: 通过表格公式，从 '月度明细 sheet' 同步，这部分是微信、支付宝可查的账单
- 额外开支: 有些开支没有通过支付宝、微信，例如现金支出、信用卡直接支出等。额外开支 = 上月结余 + 当月收入 - 房贷/车贷 - 日常 - 当月结余
- 结余: 从 '结余表 sheet' 同步。

# gpt 分类资料
- https://platform.openai.com/examples
- https://github.com/openai/openai-quickstart-python
- https://platform.openai.com/docs/guides/gpt/completions-api
- https://platform.openai.com/docs/api-reference/images

# 使用方式

1. python3 -m venv venv
2. source venv/bin/activate
3. pip install -r requirements.txt
4. python3 bill_classifier/main.py --config_file=config/config.ini

# 近期 TODO
- 增加前端 UI
- gpt 使用英文替换中文
