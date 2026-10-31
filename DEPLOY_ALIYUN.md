# 阿里云重新部署指南

> 目标：把「聚能腐植酸课题组知识库」重新部署到阿里云，并复用原有域名。
> 本文命令均在 Linux 服务器（Ubuntu 22.04）上执行，本机操作单独标注。

---

## 0. 关键结论与前提

- **域名可以复用**：域名是独立资产，与服务器无关。只要域名还在你名下、没到期，就能重新指向新服务器。
- **备案**：大陆地域（华东/华北/华南）服务器绑定域名必须已通过 **ICP 备案**；香港/新加坡等境外地域**免备案**。沿用你之前服务器的地域和备案状态即可。
- **本项目的数据不在 GitHub 上**（`data/`、`hf_cache/models/`、`chat_history/`、`.env` 都被 gitignore），必须从本机手动迁移，否则新部署是空的。

---

## 1. 购买服务器

阿里云控制台 → **ECS** 或 **轻量应用服务器**，按以下建议选：

| 项目 | 建议 |
|---|---|
| 地域 | 沿用之前（大陆需备案 / 境外免备案） |
| 镜像 | Ubuntu 22.04 |
| CPU | 2 核 |
| 内存 | **≥ 4GB**（重排模型要加载进内存） |
| 系统盘 | **≥ 40GB**（torch + 模型 + 数据） |
| 带宽 | 按需（5M 起步够用） |

> **低配省钱选项（演示模式）**：如果只是面试演示，可买 **2核2G**，并在 `.env` 里设 `ENABLE_RERANKER=false` 跳过重排器——内存实测约 700MB，2G 完全够用，且无需迁移 `hf_cache/models/`（1.1GB 模型不加载）。

拿到 **公网 IP** 后，用 SSH 登录（阿里云控制台 / 本地终端均可）。

---

## 2. 安装 Docker（服务器上）

```bash
curl -fsSL https://get.docker.com | sh
apt-get install -y docker-compose-plugin
docker --version && docker compose version
```

---

## 3. 拉取代码（服务器上）

```bash
git clone https://github.com/lelebuaichi/humic-rag-knowledge-base.git
cd humic-rag-knowledge-base
```

---

## 4. 迁移数据（⚠️ 最关键，漏了就是空库）

### 4.1 本机打包

在本机项目目录（`D:\Python\langchain\RAG项目案例`）执行：

```bash
# Windows 自带 tar（Git Bash 或 PowerShell 均可）
tar czf data.tar.gz data/
tar czf models.tar.gz hf_cache/models/
tar czf history.tar.gz chat_history/
```

### 4.2 上传到服务器

```bash
# 在本机执行（scp 到服务器，替换成你的公网 IP）
scp data.tar.gz models.tar.gz history.tar.gz root@<服务器IP>:/root/humic-rag-knowledge-base/
```

> 不习惯命令行的话，也可以用 **WinSCP / FileZilla** 图形界面，把上面三个目录直接拖到服务器项目目录。

### 4.3 服务器上解压

```bash
cd /root/humic-rag-knowledge-base
tar xzf data.tar.gz
tar xzf models.tar.gz
tar xzf history.tar.gz
```

解压后确认目录存在：`data/`、`hf_cache/models/bge-reranker-base/`、`chat_history/`。

---

## 5. 配置密钥（服务器上）

```bash
cp .env.example .env
nano .env
```

填入两个 key（内容与你本机 `.env` 一致）：

```
DEEPSEEK_API_KEY=sk-你的DeepSeekkey
DASHSCOPE_API_KEY=sk-你的DashScope key
HF_ENDPOINT=https://hf-mirror.com
ENABLE_RERANKER=false
```

> ⚠️ `.env` 含真实密钥，已被 gitignore，**绝不能提交到 GitHub**。

---

## 6. 构建并启动（服务器上）

```bash
cd /root/humic-rag-knowledge-base
docker compose up -d --build
```

首次构建会下载依赖（torch 等，约几分钟，走清华 pip 镜像）。

查看状态：

```bash
docker compose ps          # 应显示 healthy
docker compose logs -f     # 看启动日志，Ctrl+C 退出
```

---

## 7. 验证是否正常

```bash
# 本机健康检查
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8501/_stcore/health
# 应返回 200
```

然后用浏览器访问 `http://<服务器IP>:8501`，用 `admin` 登录，问一个问题测试。

---

## 8. 域名解析（阿里云控制台）

阿里云控制台 → **云解析 DNS** → 选择你的域名 → 添加记录：

| 记录类型 | 主机记录 | 记录值 |
|---|---|---|
| A | `@` | 新服务器公网 IP |
| A | `www` | 新服务器公网 IP |

生效通常几分钟（TTL 越短越快）。

---

## 9. 安全组放行端口（阿里云控制台）

ECS/轻量服务器 → **安全组** → 放行：

- `80`（HTTP）
- `443`（HTTPS）
- `8501`（Streamlit 直连，调试用；正式上线可只留 80/443）

---

## 10. 反向代理 + HTTPS（用域名访问，走 80/443）

Streamlit 依赖 **WebSocket**，反代必须支持 WebSocket 升级。推荐 **Caddy**（自动签发 HTTPS，免配置证书）。

```bash
apt-get install -y caddy
```

编辑 `/etc/caddy/Caddyfile`：

```
你的域名.com {
    reverse_proxy localhost:8501
}
```

启动：

```bash
systemctl enable --now caddy
systemctl reload caddy
```

之后即可用 `https://你的域名.com` 访问，Caddy 自动申请并续期 HTTPS 证书。

> 若用 **nginx** 替代，`location /` 里必须加：
> ```nginx
> proxy_set_header Upgrade $http_upgrade;
> proxy_set_header Connection "upgrade";
> ```
> 否则页面会一直转圈连不上。

---

## 11. 常见问题排查

| 现象 | 原因 / 处理 |
|---|---|
| 页面能打开但问答报「未检测到 DEEPSEEK_API_KEY」 | `.env` 没配或没填对，检查 `docker compose exec app env` |
| 检索报错、日志里有 reranker/CrossEncoder 错误 | `hf_cache/models` 没迁过去，或 `compose.yaml` 挂载路径不对 |
| 知识库是空的 | `data/` 没迁过去（Chroma 向量 + SQLite 都在里面） |
| 域名能解析但打不开 | 安全组没放行 80/443，或备案未通过（大陆节点） |
| 登录提示用户不存在 | `data/app.db` 没迁过去（用户表在里面） |
| 页面一直转圈 | 反代没配 WebSocket 升级头 |

---

## 12. 迁移完成后（建议）

- 修改 `admin` 默认密码：服务器上执行 `docker compose exec app python reset_password.py`（若镜像里还没有该脚本，先在本机跑 `reset_password.py`，或重建镜像后执行）。
- 定期备份：`data/`、`chat_history/` 是全部业务数据，建议定期打包备份到别处。
