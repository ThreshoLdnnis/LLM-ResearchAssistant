# LLM 财报与研报智能投研助手

上传金融 PDF，检索原文并打开对应页，导出财务数据，比较检索方法与模型答案。这个中文研究原型以招商银行为例，贯通年度报告摘要、三季报、分红实施公告和券商年报点评四类材料。本地运行。

**先看一条可以核验的结果。** 招商银行年报摘要第 3 页显示，集团 2024 年净利润为 149,559 百万元，归属于本行股东的净利润为 148,391 百万元。模型在跨年问答中混用了这两个口径。工作台提供带行名和页码的年度数据导出，可以直接回表检查。[原始 PDF，第 3 页](https://static.cninfo.com.cn/finalpage/2025-03-26/1222895153.PDF#page=3) · [实验报告](docs/STUDY.md)

## 从一次查询开始

以下命令在仓库根目录运行，已在 Windows、Python 3.12 环境验证。macOS/Linux 将激活命令换为 `source .venv/bin/activate`。

```powershell
git clone https://github.com/ThreshoLdnnis/LLM-ResearchAssistant.git
cd LLM-ResearchAssistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m finrag demo
python -m finrag ask "年报摘要如何解释负债总额增长？" --doc cmb-fy24 --mode bm25
python -m finrag series cmb-fy24 revenue net_profit parent_profit
python -m finrag serve
```

打开 [本机工作台](http://127.0.0.1:8765)。文档库支持上传有文字层的 PDF，填写公司、年份、类型和发布日期，按文档筛选查询，打开 PDF 原页，下载财务指标、经营信息候选原文和表格候选行。样本导入器按 [来源清单](data/sources.json) 下载并核验 SHA-256，原件、向量和数据库存储在本机。

## 检索、抽取与生成

```powershell
python -m scripts.fetch_encoder
python -m finrag ask "东莞证券如何解释存款成本下降？" --mode rerank --chunking semantic
python -m finrag extract --doc cmb-fy24 --kind financial --page 3 --out metrics.json
python -m finrag extract --doc cmb-note --kind narrative --out broker.json
```

BGE 编码器使用固定修订版的 ONNX 量化权重，可通过 HF_ENDPOINT 指定模型镜像。四种检索入口依次是 bm25、vector、hybrid、rerank。hybrid 用倒数排名融合（RRF），rerank 在融合候选中用局部词项覆盖度重排。分块可选定长、版面结构和基于相邻片段向量相似度的语义分块。

LLM 通过兼容 Chat Completions 的服务接入。默认地址为本机 8080 端口。以下是使用 llama.cpp **另开终端启动服务后**的示例，模型文件由使用者下载。参考实验使用 Qwen2.5 Instruct 的 Q4_K_M 版本及 llama.cpp b12780。公共模型链接见实验报告。网页仅在勾选生成模式后调用模型，命令行使用 `--generate`。

```powershell
llama-server -m path/to/qwen2.5-1.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 -c 4096 -t 5 -np 1 --alias local
```

```powershell
$env:FINRAG_BASE_URL="http://127.0.0.1:8080/v1"
$env:FINRAG_MODEL="local"
python -m finrag ask "三季报流动性覆盖率表中，季度平均值采用多少天？" --doc cmb-q324 --mode hybrid --generate
```

远程服务可通过 FINRAG_API_KEY 传入密钥。输入、输出每百万 token 的费率分别由 FINRAG_INPUT_USD_PER_M 和 FINRAG_OUTPUT_USD_PER_M 指定；缺少用量或费率时，生成成本返回 null。仅支持 JSON 对象的服务可设 FINRAG_JSON_MODE=object。每条生成论断返回模型选择的原文片段和页码，模型可能选错片段，详见逐题评估。

## 复现实验

```powershell
python -m unittest discover -s tests -v
python -m bench.evaluate --output data/local/replication
python -m bench.score_answers
python -m bench.generate data/local/new-model.json
```

最后一条使用当前配置的模型生成新输出。发布的评分绑定到已审阅输出的哈希，换模型或重新生成后需要逐题重新评分。建议用只含四份样本的库复现生成实验。

| 从哪里看 | 内容 |
|---|---|
| [学习路线](docs/MENTOR.md) | 从手工核数到独立设计外部验证集 |
| [实证研究报告](docs/STUDY.md) | 研究问题、对照实验、答案审阅、失败案例、外推边界 |
| [系统实现](finrag) | PDF 入库、检索、生成、指标与年度序列 |
| [评测集与评分](bench) | 页码相关性、财务单元格、答案与引文标注 |
| [实验输出](results) | 聚合指标、逐题排名、两种模型输出与用量 |

