# SwitchRoomMatcher

单机 Dedicated Server **下载 + 房间调度**：**一进程一房间一端口**。

对接 Unity DS 约定：

- 启动参数：`-port 7777`
- 就绪输出：`DS_READY <ip>:<port>`

仅依赖 **Python 3.6+ 标准库** + `curl` + `unzip`（兼容 CentOS 默认 python3）。  
DS 以 **单个 zip** 放在腾讯云 COS（公有读）；本仓库不管打包/上传。

## Linux 部署

机器要求：`python3`（>=3.6）、`curl`、`unzip`；放行 **TCP 1096**（API）和 **UDP 7777-7780**（最多 4 个房间）。

```bash
# CentOS
yum install -y git curl python3 unzip

git clone https://github.com/yueh0607/SwitchRoomMatcher.git
cd SwitchRoomMatcher
chmod +x scripts/*.sh

# 先把 ds.zip 传到 COS 桶根目录（见下方），再：
./scripts/deploy_linux.sh <你的服务器IP>
```

后台（SSH 断开也继续跑）：

```bash
./scripts/download_ds.sh          # 首次需要
./scripts/start_daemon.sh <你的服务器IP>
curl -s http://127.0.0.1:1096/health
./scripts/stop_daemon.sh          # 停止
# 日志: matcher.log
```

或用 systemd（开机自启）：

```bash
# 编辑 deploy/switch-room-matcher.service 里的路径/IP 后：
cp deploy/switch-room-matcher.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now switch-room-matcher
systemctl status switch-room-matcher
```

## DS 压缩包（COS）

默认下载地址：

`https://switch-ds-1302238740.cos.ap-guangzhou.myqcloud.com/ds.zip`

用 COSBrowser 把本地打好的 `ds.zip` 上传到桶 `switch-ds-1302238740` **根目录**，对象名：`ds.zip`。  
zip 内应为：

```text
SwitchGame.x86_64
UnityPlayer.so
SwitchGame_Data/...
```

Linux 下载：

```bash
./scripts/download_ds.sh
# 可选: DS_ZIP_URL=https://..../ds.zip DS_DIR=./ds ./scripts/download_ds.sh
```

## 启动调度

```bash
python3 -m ds_launcher \
  --ds-binary ./ds/SwitchGame.x86_64 \
  --port-min 7777 \
  --port-max 7780 \
  --max-rooms 4 \
  --public-host 203.0.113.10 \
  --api-port 1096
```

## HTTP API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 + 容量统计 |
| `POST` | `/rooms` | 创建房间（必填 `name`），拉起 DS |
| `GET` | `/rooms` | 房间列表 |
| `GET` | `/rooms/{id}` | 查询房间 |
| `DELETE` | `/rooms/{id}` | 关房回收 |
| `POST` | `/ds/update` | 重新从 COS 下载 `ds.zip` 并覆盖本地 DS |

### 更新 DS

有活跃房间时默认拒绝；`force=true` 会先停房再更新。

```bash
# 无活跃房间
curl -s -X POST http://127.0.0.1:1096/ds/update

# 强制停房并更新
curl -s -X POST http://127.0.0.1:1096/ds/update \
  -H "Content-Type: application/json" \
  -d '{"force":true}'
```

若启动时设置了 `DS_ADMIN_TOKEN`，请求需带：

```bash
curl -s -X POST http://127.0.0.1:1096/ds/update \
  -H "X-Admin-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"force":true}'
```

```bash
curl -s -X POST http://127.0.0.1:1096/rooms \
  -H "Content-Type: application/json" \
  -d '{"name":"朋友局-1"}'
```

## 注意

- 单机分配器；多机各跑一份再由上层选机器。
- `--public-host` 把 DS 内网 IP 改写成客户端可连地址。
- 更新 DS：替换 COS 上的 `ds.zip`，再跑一次 `./scripts/download_ds.sh`。
