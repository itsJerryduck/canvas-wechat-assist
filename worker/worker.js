/**
 * ⚔️ Canvas 日课提醒 · Telegram 接线员（Cloudflare Worker）
 * ------------------------------------------------------------------
 * 它负责三件事：
 *   1. 接收 GitHub Actions 推送来的今日任务清单（POST /push?key=...）
 *   2. 发一张带按钮的卡片到你的 Telegram
 *   3. 接收按钮点击（POST /telegram?key=...），实时改写卡片并记录 EXP / 连胜
 *
 * 配置（优先读 Worker 变量，其次读 KV 命名空间 QUEST_KV 里的条目）：
 *   BOT_TOKEN → Telegram 机器人 Token
 *   CHAT_ID   → 你的 chat_id
 *   PUSH_KEY  → 你自编的一串乱码（门禁口令，防止别人乱调你的接口）
 *
 * 绑定要求：KV 命名空间，变量名必须是 QUEST_KV
 * ------------------------------------------------------------------
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const cfg = await loadConfig(env);

    if (!cfg.BOT_TOKEN || !cfg.CHAT_ID) {
      return json({ ok: false, error: '缺少配置：请在 KV（QUEST_KV）里添加 BOT_TOKEN 和 CHAT_ID' }, 500);
    }

    // ① GitHub 脚本 → 推送今日清单
    if (url.pathname === '/push') {
      if (!cfg.PUSH_KEY || url.searchParams.get('key') !== cfg.PUSH_KEY) {
        return json({ ok: false, error: 'key 不正确' }, 403);
      }
      if (request.method !== 'POST') {
        return json({ ok: false, error: '请用 POST' }, 405);
      }
      try {
        return json(await handlePush(await request.json(), env, cfg));
      } catch (e) {
        return json({ ok: false, error: String(e) }, 500);
      }
    }

    // ② Telegram 按钮回调
    if (url.pathname === '/telegram') {
      if (!cfg.PUSH_KEY || url.searchParams.get('key') !== cfg.PUSH_KEY) {
        return new Response('forbidden', { status: 403 });
      }
      try {
        const update = await request.json();
        if (update.callback_query) ctx.waitUntil(handleCallback(update.callback_query, env, cfg));
      } catch (e) { /* 忽略解析错误 */ }
      return new Response('ok');
    }

    return new Response('🤖 Canvas Quest Bot is running.');
  },
};

/* ---------------- 配置读取 ---------------- */

async function loadConfig(env) {
  const keys = ['BOT_TOKEN', 'CHAT_ID', 'PUSH_KEY'];
  const cfg = {};
  for (const k of keys) {
    let v = env[k];
    if (!v && env.QUEST_KV) {
      try { v = await env.QUEST_KV.get(k); } catch (e) { v = null; }
    }
    cfg[k] = v == null ? '' : String(v).trim();
  }
  return cfg;
}

/* ---------------- 基础工具 ---------------- */

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}

async function tg(cfg, method, body) {
  const r = await fetch(`https://api.telegram.org/bot${cfg.BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  return await r.json();
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function getStats(env) {
  const raw = await env.QUEST_KV.get('stats');
  return raw ? JSON.parse(raw) : { exp: 0, streak: 0, lastDate: null };
}

async function saveState(env, state) {
  await env.QUEST_KV.put('state', JSON.stringify(state));
}

/* ---------------- 卡片渲染 ---------------- */

function buildCard(state, stats) {
  const total = state.tasks.length;
  const doneN = state.tasks.filter((t) => state.done[t.id]).length;
  let filled = total ? Math.round((doneN * 10) / total) : 0;
  if (filled > 10) filled = 10;
  const bar = '█'.repeat(filled) + '░'.repeat(10 - filled);

  let out = `<b>⚔️ 冒险者日志 · ${esc(state.date)}</b>\n`;
  out += `🏰 今日日课  <b>${doneN}/${total}</b>  ${bar}\n`;
  out += `✨ EXP ${stats.exp} · 🔥 连胜 ${stats.streak} 天\n`;

  const block = (list, title) => {
    if (!list.length) return '';
    let s = `\n<b>${title}</b>\n`;
    for (const t of list) {
      const mark = state.done[t.id] ? '✅' : (state.later[t.id] ? '⏰' : '⬜');
      const name = state.done[t.id] ? `<s>${esc(t.name)}</s>` : esc(t.name);
      s += `${mark} ${t.icon} ${name}\n`;
      if (!state.done[t.id]) s += `　　<i>截止 ${esc(t.due_str)} · 还剩 ${esc(t.left)}</i>\n`;
    }
    return s;
  };

  out += block(state.tasks.filter((t) => t.kind === 'main'), '⚔️ 主线任务 · Boss 战');
  out += block(state.tasks.filter((t) => t.kind === 'daily'), '📜 每日日常');

  if (state.overdue) out += `\n💀 已过期（近两周）：${state.overdue} 项`;
  if (!total) out += '\n🏖️ 今日无任务，尽情摸鱼吧！';
  out += '\n\n👉 点下面的按钮打勾 / 延后';
  return out;
}

function buildKeyboard(state) {
  const rows = [];
  state.tasks.slice(0, 12).forEach((t, i) => {
    const short = t.name.length > 14 ? t.name.slice(0, 14) + '…' : t.name;
    if (state.done[t.id]) {
      rows.push([
        { text: `✅ ${short}`, callback_data: `d|${i}` },
        { text: '↩️ 撤销', callback_data: `u|${i}` },
      ]);
    } else {
      rows.push([
        { text: `⬜ ${short}`, callback_data: `d|${i}` },
        { text: state.later[t.id] ? '⏰ 已延后' : '⏰ 延后', callback_data: `l|${i}` },
      ]);
    }
  });
  rows.push([{ text: '🔄 刷新卡片', callback_data: 'r|0' }]);
  return rows;
}

/* ---------------- 处理推送 ---------------- */

async function handlePush(payload, env, cfg) {
  const state = {
    date: payload.date || '',
    tasks: payload.tasks || [],
    overdue: payload.overdue || 0,
    done: {},
    later: {},
    gained: {},
    message_id: null,
  };
  const stats = await getStats(env);

  const resp = await tg(cfg, 'sendMessage', {
    chat_id: cfg.CHAT_ID,
    text: buildCard(state, stats),
    parse_mode: 'HTML',
    disable_web_page_preview: true,
    reply_markup: { inline_keyboard: buildKeyboard(state) },
  });

  if (!resp.ok) return { ok: false, error: resp.description || '发送失败' };

  state.message_id = resp.result.message_id;
  await saveState(env, state);
  return { ok: true, message_id: state.message_id, tasks: state.tasks.length };
}

/* ---------------- 处理按钮点击 ---------------- */

async function handleCallback(cq, env, cfg) {
  const raw = await env.QUEST_KV.get('state');
  if (!raw) return answerCq(cfg, cq.id, '还没有任务清单哦');

  const state = JSON.parse(raw);
  const [action, idxStr] = String(cq.data || '').split('|');
  const i = parseInt(idxStr, 10);
  const task = state.tasks[i];
  const stats = await getStats(env);
  let toast = '';

  if (!task && action !== 'r') return answerCq(cfg, cq.id, '这条任务已经过期了');

  if (action === 'd') {
    if (state.done[task.id]) {
      toast = '已经完成过啦 😄';
    } else {
      state.done[task.id] = true;
      delete state.later[task.id];
      const gain = task.kind === 'main' ? 50 : 20;
      if (!state.gained[task.id]) {
        stats.exp += gain;
        state.gained[task.id] = gain;
      }
      toast = `✅ ${task.name}  +${gain} EXP`;
      if (Object.keys(state.done).length === state.tasks.length && state.tasks.length) {
        if (stats.lastDate !== state.date) {
          stats.streak += 1;
          stats.lastDate = state.date;
        }
        toast = `🎉 今日全部完成！+${gain} EXP · 连胜 ${stats.streak} 天 🔥`;
      }
    }
  } else if (action === 'u') {
    delete state.done[task.id];
    toast = '已撤销';
  } else if (action === 'l') {
    if (state.later[task.id]) { delete state.later[task.id]; toast = '已取消延后'; }
    else { state.later[task.id] = true; toast = '⏰ 已标记延后'; }
  } else if (action === 'r') {
    toast = '已刷新';
  }

  await env.QUEST_KV.put('stats', JSON.stringify(stats));
  await saveState(env, state);

  await tg(cfg, 'editMessageText', {
    chat_id: cq.message.chat.id,
    message_id: cq.message.message_id,
    text: buildCard(state, stats),
    parse_mode: 'HTML',
    disable_web_page_preview: true,
    reply_markup: { inline_keyboard: buildKeyboard(state) },
  });

  return answerCq(cfg, cq.id, toast || 'OK');
}

async function answerCq(cfg, id, text) {
  return tg(cfg, 'answerCallbackQuery', { callback_query_id: id, text });
}
