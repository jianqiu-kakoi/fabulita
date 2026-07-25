# My English · CloudBase 上线版 V0

这是 My English 的大陆部署入口。它保留原学习页的离线能力，并增加：

- 中国大陆手机号验证码登录；
- 登录用户独立的本地缓存；
- CloudBase 双向进度同步和跨设备冲突合并；
- 酒店场景服务端 LLM 复核；
- 未登录或云端失败时的本地降级。

当前代码和测试已完成，但**尚未部署，也没有写入任何真实环境 ID、域名或密钥**。

## 目录

- `src/main.js`：登录、账号切换和页面外壳。
- `src/sync.js`：本地/云端双向同步和账号隔离。
- `backend/src/`：`my-english-api` 云函数。
- `backend/src/rubrics.ts`：酒店六题的服务端判分规则。
- `privacy.html`：上线前必须补齐运营者和模型服务商信息的隐私说明。
- `cloudbaserc.json`：云函数部署配置。
- `cloud-function-security-rules.json`：控制台可直接复制的函数调用规则。

## 数据流

未登录时，学习页只使用浏览器本地存储。首次登录后，访客数据只会认领给
第一个账号一次；此后每个 CloudBase UID 使用独立命名空间，A 退出后 B 登录
不会上传 A 的本地记录。

登录后的同步顺序是：

1. 客户端分批上传不可变学习事件和当前快照；
2. 云函数从调用上下文读取 UID，不接受客户端 `userId`；
3. 服务端事务内去重事件并按题目、卡片、问题合并 checkpoint；
4. 客户端拉取 canonical checkpoint，合并进当前账号的本地缓存；
5. reset 和 Q&A 删除使用 tombstone，旧设备不能把数据复活。

本地判分为 `correct` 或 `near_miss` 时不会调用 LLM。只有酒店文本题被本地判为
`incorrect` 且用户已登录时才调用服务端；超时或服务故障会回退本地结果，
并且一次提交只记录一个最终 attempt。

## 本地验证

先在仓库根目录重新生成学习页：

```sh
.venv/bin/python scripts/build_docs.py
```

再安装和验证 CloudBase 项目：

```sh
cd deploy/my-english-cloudbase
npm install
npm --prefix backend install
npm run check
```

本地预览：

```sh
cp .env.example .env.local
# 在 .env.local 填写真实 VITE_CLOUDBASE_ENV_ID
npm run dev
```

未填写环境 ID 时页面仍可学习，但登录按钮会禁用、进度只保存在本机。

## CloudBase 控制台准备

1. 创建**上海地域**环境；短信 OTP 目前只支持上海。
2. 在「身份认证 → 登录方式 → 常规登录」开启短信验证码。
3. 创建三个文档数据库集合，并全部设为浏览器不可直接读写：
   - `learning_events`
   - `learning_checkpoints`
   - `learning_rate_limits`
4. 为 `learning_events` 创建升序复合索引：
   `ownerKey + scope + sequence`。
5. 在云函数「权限控制」设置：

```json
{
  "*": {
    "invoke": false
  },
  "my-english-api": {
    "invoke": "auth.loginType != 'ANONYMOUS' && auth != null"
  }
}
```

CloudBase 要求规则中必须包含 `*`；这里先默认拒绝其他函数，再只为
`my-english-api` 开放已登录且非匿名的客户端调用。

6. 在环境「安全来源/安全域名」加入正式域名和需要使用的测试域名。
7. 在云函数环境变量中配置：

```text
LLM_API_KEY
LLM_MODEL
LLM_BASE_URL
LLM_TIMEOUT_MS=4000
LLM_RATE_LIMIT_PER_MINUTE=10
```

`LLM_BASE_URL` 必须是明确选择的 HTTPS、OpenAI-compatible 接口。大陆上线不设
默认海外服务商；应先确定服务商、数据处理地域，并写入 `privacy.html`。
手机号、CloudBase UID 和服务端密钥都不会进入 LLM 请求。

## 构建与部署

当前配置不写死环境 ID，部署时必须用 `-e` 明确指定，避免误发到别的环境：

```sh
cd deploy/my-english-cloudbase
npm run check
# 本机尚未安装 tcb 时先执行：
npm install -g @cloudbase/cli
tcb login
tcb fn deploy my-english-api -e <env-id>
tcb hosting deploy dist -e <env-id>
```

`backend/dist/` 是云函数的实际 handler，已由测试构建并应随部署包上传；
根目录的 `dist/` 才是静态网站产物。

部署后用 `tcb hosting detail -e <env-id>` 查看默认访问地址。绑定自定义域名时，
CloudBase 官方要求先完成 ICP 备案。

## 正式开放注册前的发布门槛

- 把 `privacy.html` 里的运营者、联系邮箱、模型服务商和处理地域补全；
- 实测短信发送、首次登录、退出、A/B 账号隔离和两台设备同步；
- 验证数据库为 admin-only，函数权限拒绝未登录和匿名身份；
- 验证 LLM Key 不出现在 `dist/`、浏览器网络响应或 Git；
- 配置日志告警、费用告警、短信额度与模型调用额度；
- 在页脚展示实际 ICP 备案号并链接工信部备案系统；
- 若以后收费、广告化、以组织名义运营或内容超出个人性质，先迁移为单位主体，
  不要继续依赖个人备案。

## 个人备案说明

个人备案不会改变代码、教材改编内容或产品品牌的权利归属；备案是网站主办者
登记，不是著作权转让。不过，是否能以个人主体上线取决于网站实际内容和所在省
管局口径。腾讯云当前说明要求个人网站内容与个人性质相符，不能包装成企业、
团体、论坛或需要前置审批的服务。这个 V0 可以作为个人开源学习工具申请，
但“能否通过”不能在代码层保证。

官方参考：

- [CloudBase Web V3 身份认证](https://docs.cloudbase.net/api-reference/webv3/authentication)
- [CloudBase 云函数安全规则](https://docs.cloudbase.net/cloud-function/security-rules)
- [CloudBase 静态托管部署](https://docs.cloudbase.net/cli-v1/hosting)
- [腾讯云 ICP 备案网站信息要求](https://cloud.tencent.com/document/faq/243/19644)
