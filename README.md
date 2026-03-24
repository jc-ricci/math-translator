# 数学文献PDF翻译系统

将德语/法语/英语数学PDF扫描件翻译为中文PDF，保留完整LaTeX数学公式。

## 流水线

1. **上传PDF** → 按50页分块
2. **Nougat OCR** → 识别为Markdown+LaTeX (`.mmd`)
3. **Claude API翻译** → 中文（现代数学语言）
4. **XeLaTeX编译** → 输出中文PDF

## 安装

### 系统依赖

```bash
# macOS
brew install mactex poppler

# Ubuntu/Debian
apt-get install texlive-full poppler-utils
```

### Python依赖

```bash
pip install -r requirements.txt
```

### 环境配置

```bash
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY
```

## 启动

```bash
cd backend
uvicorn main:app --reload --port 8000
```

访问 http://localhost:8000

## 使用

1. 打开浏览器访问 http://localhost:8000
2. 拖拽或点击上传数学PDF文件（最大500MB）
3. 选择源语言（德语/法语/英语）和目标语言
4. 等待处理完成（进度实时显示）
5. 下载翻译后的PDF或LaTeX源码

## 注意事项

- Nougat在CPU上较慢（50页约5-10分钟），建议使用GPU
- 需要安装XeLaTeX和ctex包（包含在texlive-full/mactex中）
- 对于超大PDF（>500页），处理时间可能超过2小时
