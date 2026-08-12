# SwitchRoomMatcher

单机 Dedicated Server **下载 + 房间调度**：**一进程一房间一端口**。

对接 Unity DS 约定：

- 启动参数：`-port 7777`
- 就绪输出：`DS_READY <ip>:<port>`

仅依赖 **Python 3.10+ 标准库** + `curl`（下载），无需 pip。  
DS 已放在腾讯云 COS（公有读）；本仓库**不管打包/上传**。

## Linux 部署

机器要求：`python3`、`curl`；放行 **TCP API 端口**（默认 8080）和 **UDP 游戏端口段**（默认 7777-7877）。

```bash
git clone https://github.com/yueh0607/SwitchRoomMatcher.git
cd SwitchRoomMatcher
chmod +x scripts/*.sh

# 公网/局域网 IP：客户端用来连房间的地址
./scripts/deploy_linux.sh <你的服务器IP>
```

分步也可以：

```bash
./scripts/download_ds.sh
./scripts/start.sh <你的服务器IP>
```

后台跑可用：

```bash
nohup ./scripts/start.sh <你的服务器IP> > matcher.log 2>&1 &
curl -s http://127.0.0.1:8080/health
```

创房验证：

```bash
curl -s -X POST http://127.0.0.1:8080/rooms \
  -H "Content-Type: application/json" \
  -d '{"name":"test-1"}'
```

## 下载 DS（COS）

默认桶：`switch-ds-1302238740`（`ap-guangzhou`），对象在桶根目录（`SwitchGame.x86_64`、`UnityPlayer.so`、`SwitchGame_Data/...`）。  
文件列表见 `scripts/ds_manifest.txt`。

```bash
chmod +x scripts/download_ds.sh
./scripts/download_ds.sh
# 可选: DS_BASE_URL=https://.... DS_DIR=./ds ./scripts/download_ds.sh
```

## 启动调度

```bash
python3 -m ds_launcher \
  --ds-binary ./ds/SwitchGame.x86_64 \
  --port-min 7777 \
  --port-max 7877 \
  --max-rooms 32 \
  --public-host 203.0.113.10 \
  --api-port 8080
```

环境变量：`DS_BINARY`、`DS_PORT_MIN`、`DS_PORT_MAX`、`DS_MAX_ROOMS`、`DS_PUBLIC_HOST`、`DS_API_PORT`、`DS_EXTRA_ARGS`。  
默认额外参数：`-batchmode -nographics -logFile -`。

## HTTP API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 + 容量统计 |
| `POST` | `/rooms` | 创建房间（必填 `name`），拉起 DS，返回 `endpoint` |
| `GET` | `/rooms` | 房间列表 |
| `GET` | `/rooms/{id}` | 查询房间 |
| `DELETE` | `/rooms/{id}` | 杀掉对应 DS，回收端口 |

### 创房 / 列表 / 关房

```bash
curl -s -X POST http://127.0.0.1:8080/rooms \
  -H "Content-Type: application/json" \
  -d '{"name":"朋友局-1"}'

curl -s http://127.0.0.1:8080/rooms
curl -s -X DELETE http://127.0.0.1:8080/rooms/<room_id>
```

## 注意

- 单机分配器；多机请各跑一份再由上层选机器。
- `--public-host` 把 DS 内网 IP 改写成客户端可连地址。
- 防火墙放行 UDP 游戏端口与 API 端口。
- COS 上 DS 文件有增减时，更新 `scripts/ds_manifest.txt` 后重新下载。
