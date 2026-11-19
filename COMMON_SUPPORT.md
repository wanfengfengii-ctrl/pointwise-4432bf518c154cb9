# 分批上线模型的共同测次复核

白班按指定评分修订交件。夜班在独立归档中选件并指定模型顺序，按实际共同获评的测次核算。V1 完整双模型流程继续沿用 README.md。下列新增入口从 `review` 导入，并使用原有 `open_source` 和 `open_archive`。新旧接口中的编号各在自己的业务范围内解释。

## 录入与历史

`record_sparse_scores(source, station, ticket, occurrence, label, submission_id, scores)` 返回一个可供本接口冻结的正整数修订。先用 `admit_board` 登记本站送测资格。站号、中心票、站内测次号、提交号和模型名沿用 V1 标识规则。`scores` 为非空模型名到分数的映射，分数接受非布尔整数、`Fraction` 或 V1 有理数字符串。

在稀疏评分中，同站同测次首记固定中心票和 `positive` 或 `negative` 标签。同站同提交号按测次、票、标签及本次提交的完整分数映射核对，映射顺序和有理数写法无关。等价重投返回自己的原修订，异参或更改既定票、标签抛 `Conflict`。非法输入抛 `InvalidInput`，缺送测资格抛 `MissingItem`。不同提交可补分或更正。冻结指定修订时，每个模型取该站该测次截至该修订最后提交的值，未提交则缺席，零是有效分数。V1 和稀疏评分可并存，各自冻结本版输入。冻结未知的站点稀疏修订抛 `MissingItem`。

## 固定站件

- `freeze_sparse_station(source, archive, station, revision)` 冻结到归档，返回带 `.package_id` 和 `.source` 的站件。`.source` 为原有的 `EvidenceSource`，本地修订以返回整数的十进制字符串写入来源。
- `encode_sparse_evidence(evidence)` 返回可传送的 JSON 文本。
- `accept_sparse_station(archive, payload, declared_source)` 验收该文本并返回固定站件。`declared_source` 为合作方声明的 `EvidenceSource`。
- `read_sparse_station(archive, package_id)` 按号领取归档中的稀疏站件，未知号抛 `MissingItem`。

交换文本使用 `version: 2`、`package_id`、`source` 和 `contributions` 四个字段。`source` 与 V1 一样含 `origin`、`station`、`revision` 三个标识字符串，合作站可使用自己的修订标识。`contributions` 是非空列表，每项形如 `{"ticket":"P","label":"positive","count":1,"scores":{"A":[["0",1]],"B":[["1/2",1]]}}`。`scores` 的键就是该组的完整获评模型集合，至少有一个模型。每个票、标签和完整模型集合组合至多出现一次。每列是非空的 `[有理数字符串, 重数]` 列表，等值数只列一次，各列重数合计都等于该组 `count`。重数和 `count` 为非布尔正整数。组内测次的逐行分数组合无需移交，内部表示可自由选择。

声明的来源必须与文本一致。字段重复、形状或计数错误、版本错误、无效值及冲突抛 `InvalidEvidence`，拒收时归档无新增。已有件号被不同稀疏证据占用时拒收。相同稀疏来源三元组的等价证据重投返回首个固定件号，异证据拒收。组、模型和列内数值的书写顺序以及等值分数的写法无关。来自同一站的不同修订可各自冻结。站件关闭评分库后仍可传送和领取。

## 签发与领取

`issue_common_comparison(archive, package_ids, models)` 签发。`package_ids` 沿用 V1 的件号集合输入，同件去重，至少一件且每站只选一件。`models` 为包含至少两个互异模型名的有序列表或元组。非法模型参数抛 `InvalidInput`，非法选件、未知件号或选入 V1 件抛 `InvalidSelection`。已选站件即使在筛选后贡献为零，也进入报告出处。

仅保留完整获评集合包含全部请求模型的组。共同正负测次数分别对保留组的 `count` 求和。每列沿用 V1 AUC，在合池后计算，保留重数并把同分计半。只对共同样本中出现的票做整票剔除，删去该票在所有所选站的贡献，按剩余共同样本重算每列。每次删除后仍有两类才计为有效，并按票号排序。协方差矩阵的 `(i,j)` 项等于同一批有效删板记录中，第 i、j 列各减列均值后乘积之和乘以 `(m-1)/m`，其中 m 是有效删板数。矩阵含对角项。全量缺一类或有效删板数小于二时抛 `InsufficientEvidence`。

签发返回有 `.report`、`.sources` 和 `.receipt` 的对象。`.report` 提供 `.report_id`、`.models`、`.positive_count`、`.negative_count`、`.auc`、`.deletions`、`.covariance`。模型和 AUC 用请求顺序的元组，删板为带 `.ticket` 和 `.auc` 的记录元组，协方差矩阵为按模型原序的行元组组成的元组。AUC 和矩阵元素为 `Fraction`。`.sources` 沿用 `ReportSource` 的字段，按站名排序。`.receipt` 沿用 `ReportReceipt` 的字段。

`read_common_report(archive, report_id)` 领取同样结构的固定结果，未知号抛 `MissingItem`。已签结果含请求模型顺序、完整实际选件、数值和回执。签发的全部写入同次提交。提交失败抛 `PublicationFailed`，无部分成果，可重试。领取直接使用存值，源库更正和归档重开继续兑现原号。原版读写、报告编码及回归继续运行。

## 共同覆盖示例

`python3 -B common_support_examples.py` 输出两个独立来件和手算账。新增入口可用以下调用核对其中一班。两个来件是同站不同修订，应分别签发。

```python
import json
from common_support_examples import MODELS, partner_cases
from review import EvidenceSource, accept_sparse_station, issue_common_comparison

case = partner_cases()['low']
package = case['package']
accepted = accept_sparse_station(archive, json.dumps(package), EvidenceSource(**package['source']))
delivery = issue_common_comparison(archive, [accepted.package_id], MODELS)
```

两班在 P、Q 上各有高分正例、低分正例和一条负例。A、B 都给 2、0、1，C 给覆盖的正例 2 分及负例 1 分。只把 C 的正例覆盖从高分改为低分，A、B 的共同 AUC 从 1 变为 0。两班均为两正两负，逐板仍各有一正一负。

录入示例可在同站同测次依次用 `s1` 提交 `{'A': 0, 'B': 1}`、用 `s2` 提交 `{'C': 2}`、用 `s3` 提交 `{'B': 3}`。写完三次后分别冻结旧修订。第一件缺 C，后两件依次为 `(0,1,2)`、`(0,3,2)`。此时重送 `s1` 的等价原请求仍返回首修订。用 `s3` 重送 `{'A': 0, 'B': 3}` 抛 `Conflict`，即使合并后读数相同。

跨站核账可在东、西站复用相同的 P、Q 票及同名站内测次。每站每票各一正一负，P 的 A、B 正例给 `(2,0)`，Q 给 `(0,2)`，全体负例给 `(1,1)`。选两站后共同样本为四正四负，全量为 `(1/2,1/2)`，删 P 为 `(0,1)`，删 Q 为 `(1,0)`，矩阵对角为 `1/4`，非对角为 `-1/4`。

交付时让现有 `.pointwise-runtime.json` 的验证入口运行全部原回归及新增联合核验，并使演示入口展示两班覆盖差异、断源签发和重开领取的实际结果。核验应包含签发失败后重试，可参照 `tests/support.py` 中的延迟外键提交失败夹具。简述接纳截面怎样交给冻结站件，以及报告怎样用其建立共同样本。
