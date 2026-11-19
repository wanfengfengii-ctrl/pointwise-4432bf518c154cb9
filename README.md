# 澄川薄膜检测中心判片复核台

东、西站对同一实体试板复测。检测员领中心票后分别登记送测，判片设备交来带正负标签的双模型评分，质检员核验并按需更正。白班交班员按评分修订冻结站件，夜班分析员按指定件号签发比较，班组长凭报告号领回当时的数值、选件和回执。评分源库停用后，归档库可以独立处理选件、签发和领取。

## 运行

需要 Python 3.11 和标准库。请在项目根目录执行。

```sh
python3 -B check_project.py
```

`check_project.py` 是控制台提供的完整 unittest 入口。也可以直接运行 `python3 -B -m unittest discover -s tests -v`。

```sh
python3 -B review.py demo
```

演示使用临时目录中的独立源库与归档库，从 `samples/shift.json` 接纳测次并冻结两站，关闭源库后签发比较。同时验收 `samples/foreign-stations.json` 中的反向外站件。`samples/manual-ledger.json` 保存独立手算账，演示核对实际统计与归档领取后输出两条 `POINTWISE_SCENARIO` 和两份 JSON 导出。演示随后运行 V2 共同复核：接纳 `common_support_examples.py` 的高、低覆盖两班并打印 `SPARSE_COVERAGE_SHIFT`，在本地稀疏源库冻结东西两站后关闭源库、断源签发跨站报告（`SPARSE_SOURCE_CLOSED`），再重开归档按原号领取（`SPARSE_REOPEN_CLAIM`）。

## Python API

从 `review` 可导入下列入口和类型。`open_source(path, *, origin=None)` 与 `open_archive(path)` 返回调用方负责关闭的 SQLite 连接。两库使用不同路径。首次打开源库时可指定稳定且在交班范围内唯一的来源名称，省略时生成并保存一个来源名称。后续打开沿用库中来源，显式传入冲突名称会被拒绝。重复初始化保留已有数据与更正。

| 调用 | 结果 |
| --- | --- |
| `admit_board(source, BoardTicket(number, entity), station)` | 返回该站的 `StationAdmission`。同票同实体可追加站点资格，重复送测登记返回原登记修订。同一实体使用一张中心票。 |
| `record_pair(source, station, ticket, occurrence, label, models, scores, *, correction=None)` | 返回 `ScoreRevision`，其 `revision` 可作为冻结边界。`models` 是 `ModelPair(first, second)`，`scores` 是以两名称为键的映射。`` 不属于标识。 |
| `read_station_snapshot(source, station, revision)` | 返回指定站点在该修订边界完整可见的测次版本，按站内测次号排序。 |
| `freeze_station(source, archive, station, revision)` | 返回不可变的 `StationEvidence`，其 `package_id` 可用于选件和领取。`encode_evidence(evidence)` 导出 V1 交班件。 |
| `accept_station(archive, payload, EvidenceSource(origin, station, revision))` | 验收 JSON 文本，返回固定站件。同来源修订且内容等价的重交返回已登记件号。 |
| `StationCatalog(archive).read(package_id)` | 按号返回归档中的固定站件。 |
| `issue_comparison(archive, package_ids)` | 返回包含 `report`、`sources`、`receipt` 的 `ReportDelivery`。同一件号重复引用合并，每站限一个修订，参加站件须使用相同有序模型对。 |
| `read_report(archive, report_id, *, as_json=False)` | 用 `delivery.report.report_id` 领取原 `ReportDelivery`。`as_json=True` 时返回确定性 JSON 文本，其中各有理数用 `numerator` 和 `denominator` 表示。 |

标签为 `positive` 或 `negative`，属于测次。同一试板可以具有两类测次。分数接受整数、`Fraction` 或 Python 3.11 的 `Fraction` 可解析字符串，等值有理数在重投、冻结和计算时等价。每站的第一条接纳确定该站的有序模型对。相同站号和测次号的原样重投兑现最初接纳。使用 `Correction(code)` 提交具名更正，站内同一更正号的等价重投兑现原更正修订。更正可以改变标签和分数，保留原票、站点与测次号。标识为非空、可打印且首尾无空白的字符串。

V1 站件包含 `version`、`package_id`、`models`、`source` 和 `contributions`。`source` 包含 `origin`、`station`、`revision`，均为字符串。每个 `contributions` 条目有 `ticket`、`label` 和 `scores`，其中 `scores` 是按模型顺序给出的两列 `[有理数字符串, 正整数重数]` 列表。同票同标签的两列测次数必须一致，每列每个数值一条，同票同标签一组。合作站以中心公开票号表示实体试板，归档可独立验证站件的结构、来源声明和固定身份。编码按票、标签和分数规范化。已占用的件号与不同内容冲突，等价重交兑现原号，更正后的修订另发号。

AUC 对整个合池的正负记录对求平均。正分较高、同分、较低分别记 1、1/2、0。每次剔除删除同票在所有入选站的全部贡献，并在剩余全池重算两列。只保留仍有正负两类的剔除，按票号排序。有效票数为 m 时，协方差为同票两列各减去列均值后的乘积之和乘以 `(m−1)/m`。全量缺一类或有效票少于两个时返回 `INSUFFICIENT_EVIDENCE`。报告数值使用 `Fraction`，选件排列不影响数值和出处顺序。同一轮使用不同站点时，跨站正负比较与站内比较使用同一权重。

业务异常继承 `storage.ReviewError`，以 `code` 区分 `INVALID_INPUT`、`CONFLICT`、`MISSING_ITEM`、`INVALID_STATION_EVIDENCE`、`INVALID_SELECTION`、`INSUFFICIENT_EVIDENCE`、`PUBLICATION_FAILED`。报告主体、出处和回执一次提交。签发被拒或提交失败时没有新报告或回执。报告编号在归档库内有效，旧报告可在更正、站件更新和重开后继续按原号读取。

## 夜班共同测次复核（V2 稀疏流程）

`COMMON_SUPPORT.md` 定义分批上线模型的共同获评复核，入口同样从 `review` 导入，与 V1 共用 `open_source`、`open_archive`，但使用独立的表、件号前缀（`sparse-`）和报告编号空间。

| 调用 | 结果 |
| --- | --- |
| `record_sparse_scores(source, station, ticket, occurrence, label, submission_id, scores)` | 接纳具名稀疏分数，返回可冻结的正整数修订。同站同测次首记固定票与正负标签；同提交号等价重投返回原修订，异参或更改票、标签抛 `Conflict`。不同提交可补分或更正，零是有效分数。 |
| `freeze_sparse_station(source, archive, station, revision)` | 按修订边界取每个模型的最后可见值，冻结 V2 站件并返回带 `.package_id`、`.source` 的 `SparseStationEvidence`。 |
| `encode_sparse_evidence(evidence)` / `accept_sparse_station(archive, payload, EvidenceSource(...))` | 导出或验收 `version: 2` 站件；来源声明不一致、形状计数错误或件号冲突抛 `InvalidEvidence`，拒收无新增。 |
| `read_sparse_station(archive, package_id)` | 按号领取归档中的稀疏站件。 |
| `issue_common_comparison(archive, package_ids, models)` | 对至少两个有序互异模型签发共同获评报告；同件去重、每站限一件，选入 V1 件或未知件抛 `InvalidSelection`。 |
| `read_common_report(archive, report_id, *, as_json=False)` | 按号领取固定的共同比较结果，源库更正与归档重开后仍兑现原号。 |

### 接纳截面如何交给冻结站件

稀疏录入把每次提交原样记入版本表，并在测次登记表上固定 `(站, 测次) -> (票, 标签)`。冻结指定修订时，快照器只读取修订号不晚于边界的版本，对每个 `(测次, 模型)` 保留最后一条分数；缺席的模型不补零。冻结器再按 `(票, 标签, 完整获评模型集合)` 分组，把逐行分数折叠成带重数的有理数列，各组 `count` 与每列重数合计一致。交换文本只移交分组列与重数，不移交逐行组合，因此合作方之间只共享复核所需的截面。

### 报告怎样建立共同样本

签发时先按站、件号规则选件，再仅保留完整获评集合包含全部请求模型的组；被整组筛掉的站件仍保留在报告出处中。保留组按票合池，正负测次数对 `count` 求和，每列在合池上按 V1 的同分计半规则计算精确 AUC。删板只对共同样本中出现的票做整票剔除（同步删除该票在所有入选站的贡献），删除后仍含两类才记为有效删板并按票号排序；协方差矩阵在同一批有效删板记录上按各减列均值的乘积和乘以 `(m-1)/m` 计算，含对角项。全量缺一类或有效删板不足两张抛 `InsufficientEvidence`。报告主体、出处与回执在同一事务写入，提交失败抛 `PUBLICATION_FAILED` 且无部分成果，可重试。
