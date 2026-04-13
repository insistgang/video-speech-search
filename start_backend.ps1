# 切换到项目目录
Set-Location $PSScriptRoot

# 设置环境变量
$env:API_KEY = "dev-api-key-12345"
$env:VISION_API_KEY = "e6958503387e4e0b9f005c4ddd25bbd2.pwGddhur3wLlwfIV"
$env:VISION_PROVIDER = "zhipu"
$env:VISION_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
$env:MODEL_NAME = "glm-4.6v-flashx"

# 启动后端
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
