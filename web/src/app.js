(function () {
  "use strict";

  var MAX_OUTPUT_LINES = 30;

  var activeRunId = null;
  var eventSource = null;
  var activeConversationId = null;
  var selectedSessionId = null;
  var sessions = [];
  var stats = { steps: 0, toolCalls: 0, errors: 0 };

  var $ = function (sel) { return document.querySelector(sel); };

  function esc(s) {
    if (!s) return "";
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  function fmtArgs(args) {
    if (!args || typeof args !== "object") return "{}";
    var parts = [];
    for (var k in args) {
      if (!args.hasOwnProperty(k)) continue;
      var v = args[k];
      var vStr = typeof v === "string" ? '"' + v.replace(/"/g,'\\"') + '"' : String(v);
      parts.push('<span class="arg-key">' + esc(k) + '</span>: <span class="arg-str">' + vStr + '</span>');
    }
    return "{ " + parts.join(", ") + " }";
  }

  function updateStats(elapsed) {
    $("#stat-steps").textContent = stats.steps;
    $("#stat-tools").textContent = stats.toolCalls;
    $("#stat-errors").textContent = stats.errors;
    $("#stat-errors").className = "stat-value" + (stats.errors > 0 ? " error" : "");
    $("#stat-elapsed").textContent = (elapsed || 0).toFixed(1) + "s";
    $("#trace-step").innerHTML = "step <strong>" + stats.steps + "</strong>";
    $("#trace-time").innerHTML = "<strong>" + (elapsed || 0).toFixed(1) + "s</strong>";
  }

  function setStatus(s) {
    $("#status-indicator").textContent = s;
    $("#state-status").textContent = s;
    $("#state-status").className = "state-val " + s;
    syncTopBar();
    var cancelBtn = $("#btn-cancel");
    if (cancelBtn) cancelBtn.style.display = (s === "running") ? "" : "none";
    var title = $("#trace-title");
    if (title) {
      title.textContent = s === "idle" ? "// idle" : s === "cancelled" ? "// cancelled" : "// " + s;
      title.className = "trace-title" + (s === "running" ? " active" : "");
    }
  }

  function showFinalAnswer(success, text, cancelled) {
    var banner = $("#final-answer");
    var tag = $("#final-answer-tag");
    var status = $("#final-answer-status");
    var body = $("#final-answer-body");
    if (!banner) return;
    banner.style.display = "block";
    tag.textContent = cancelled ? "CANCELLED" : (success ? "RESULT" : "ERROR");
    tag.className = "final-answer-tag" + (cancelled ? " cancelled" : (success ? " success" : " error"));
    status.textContent = success ? "completed" : (cancelled ? "user stopped" : "failed");
    body.textContent = text || "";
    body.className = "final-answer-body" + (success ? " success" : " error");
  }

  function hideFinalAnswer() {
    var banner = $("#final-answer");
    if (banner) banner.style.display = "none";
  }

  function appendTraceStep(stepNum, thought) {
    var trace = $("#trace");
    var empty = $("#trace-empty");
    if (empty) empty.style.display = "none";

    var block = document.createElement("div");
    block.className = "trace-step-block";
    block.dataset.step = stepNum;

    var numEl = document.createElement("div");
    numEl.className = "trace-step-number";
    numEl.textContent = "STEP " + String(stepNum).padStart(2, "0");

    var thoughtEl = document.createElement("div");
    thoughtEl.className = "trace-thought";
    thoughtEl.innerHTML = '<span class="trace-thought-prefix">think ▸</span>' + esc(thought);

    block.appendChild(numEl);
    block.appendChild(thoughtEl);
    trace.appendChild(block);
    trace.scrollTop = trace.scrollHeight;
    return block;
  }

  function appendToolCall(block, toolName, toolArgs) {
    var toolBlock = document.createElement("div");
    toolBlock.className = "trace-tool-block";

    var header = document.createElement("div");
    header.className = "trace-tool-header";
    header.innerHTML =
      '<span class="trace-tool-tag">CALL</span>' +
      '<span class="trace-tool-name">' + esc(toolName) + '</span>';

    var args = document.createElement("div");
    args.className = "trace-tool-args";
    args.innerHTML = fmtArgs(toolArgs);

    toolBlock.appendChild(header);
    toolBlock.appendChild(args);
    block.appendChild(toolBlock);

    document.querySelectorAll(".tool-item").forEach(function (el) {
      if (el.querySelector(".tool-name").textContent === toolName) {
        el.classList.add("active");
      }
    });

    setTimeout(function () {
      document.querySelectorAll(".tool-item").forEach(function (el) {
        el.classList.remove("active");
      });
    }, 3000);
  }

  function appendToolResult(block, data) {
    var text = data.output || (data.error || "");
    var lines = text.split("\n");
    var resBlock = document.createElement("div");
    resBlock.className = "trace-result-block" + (data.error ? " error" : "");

    var tag = data.error ? "ERR" : "OK";
    var header = document.createElement("div");
    header.className = "trace-result-header";
    header.innerHTML = '<span class="trace-result-tag">[' + tag + ']</span>';
    resBlock.appendChild(header);

    var body = document.createElement("pre");
    body.className = "trace-result-body";
    body.textContent = text;
    resBlock.appendChild(body);

    if (lines.length > MAX_OUTPUT_LINES) {
      body.style.display = "none";
      resBlock.classList.add("collapsed");
      resBlock.title = "click to expand";
      resBlock.addEventListener("click", function () {
        resBlock.classList.remove("collapsed");
        body.style.display = "";
        $("#trace").scrollTop = $("#trace").scrollHeight;
      });
    }

    block.appendChild(resBlock);
    $("#trace").scrollTop = $("#trace").scrollHeight;
  }

  function appendAnswer(block, answer) {
    var ans = document.createElement("div");
    ans.className = "trace-answer";
    ans.innerHTML = '<span class="trace-answer-prefix">▸ DONE</span>' + esc(answer);
    block.classList.add("step-final");
    block.appendChild(ans);
    $("#trace").scrollTop = $("#trace").scrollHeight;
  }

  function appendError(block, error) {
    block.classList.add("step-error");
    var resBlock = document.createElement("div");
    resBlock.className = "trace-result-block error";
    resBlock.innerHTML =
      '<span class="trace-result-tag">[ERR]</span>' + esc(error);
    block.appendChild(resBlock);
  }

  async function cancelRun() {
    if (!activeRunId) return;
    await fetch("/api/runs/" + activeRunId + "/cancel", { method: "POST" });
  }

  function connectStream(runId) {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }

    eventSource = new EventSource("/api/runs/" + runId + "/stream");

    eventSource.onerror = function () {
      eventSource.close();
    };

    eventSource.onmessage = function (e) {
      var msg;
      try { msg = JSON.parse(e.data); } catch (_) { return; }

      if (msg.type === "done") {
        eventSource.close();
        eventSource = null;
        return;
      }

      if (msg.type === "agent_start") {
        setStatus("running");
        $("#footer-cursor").textContent = "executing";
        return;
      }

      if (msg.type === "step_thought") {
        stats.steps = Math.max(stats.steps, msg.data.step);
        appendTraceStep(msg.data.step, msg.data.thought);
        updateStats();
        return;
      }

      if (msg.type === "tool_call") {
        stats.toolCalls++;
        var el = document.querySelector('[data-step="' + msg.data.step + '"]');
        if (el) appendToolCall(el, msg.data.tool_name, msg.data.tool_args);
        updateStats();
        return;
      }

      if (msg.type === "tool_result") {
        var el2 = document.querySelector('[data-step="' + msg.data.step + '"]');
        if (el2) appendToolResult(el2, msg.data);
        if (!msg.data.success) stats.errors++;
        updateStats();
        return;
      }

      if (msg.type === "step_error") {
        stats.errors++;
        var el3 = document.querySelector('[data-step="' + msg.data.step + '"]');
        if (el3) appendError(el3, msg.data.error);
        updateStats();
        return;
      }

      if (msg.type === "step_end") {
        var el4 = document.querySelector('[data-step="' + msg.data.step + '"]');
        if (el4 && msg.data.answer) appendAnswer(el4, msg.data.answer);
        return;
      }

      if (msg.type === "context_compressed") {
        var trace = $("#trace");
        var indicator = document.createElement("div");
        indicator.className = "compression-indicator";
        indicator.innerHTML =
          '<span class="compression-icon">⚡</span>' +
          '<span class="compression-text">context compressed · ' +
          msg.data.messages + ' msgs kept · ' +
          msg.data.summary_length + ' chars summarized</span>';
        trace.appendChild(indicator);
        trace.scrollTop = trace.scrollHeight;
        return;
      }

      if (msg.type === "agent_done") {
        var cancelled = msg.data.cancelled;
        setStatus(cancelled ? "cancelled" : (msg.data.success ? "done" : "failed"));
        $("#footer-cursor").textContent = cancelled ? "stopped" : (msg.data.success ? "completed" : "failed");
        showFinalAnswer(msg.data.success && !cancelled, msg.data.result, cancelled);

        var lastBlock = document.querySelector(".trace-step-block:last-child");
        if (lastBlock && msg.data.success) lastBlock.classList.add("step-final");
        if (lastBlock && !msg.data.success && !cancelled) lastBlock.classList.add("step-error");

        refreshHistory();
        refreshMemories();
        return;
      }

      if (msg.type === "cancelled") {
        setStatus("cancelled");
        $("#footer-cursor").textContent = "stopped";
        return;
      }

      if (msg.type === "agent_error") {
        setStatus("failed");
        $("#footer-cursor").textContent = "error";
        showFinalAnswer(false, msg.data.error, false);
        var trace = $("#trace");
        var empty = $("#trace-empty");
        if (empty) empty.style.display = "none";
        var errBlock = document.createElement("div");
        errBlock.className = "trace-step-block step-error";
        errBlock.innerHTML =
          '<div class="trace-step-number">FATAL</div>' +
          '<div class="trace-result-block error">' +
          '<span class="trace-result-tag">[ERR]</span>' +
          esc(msg.data.error) + "</div>";
        trace.appendChild(errBlock);
      }
    };
  }

  function clearTrace() {
    var trace = $("#trace");
    trace.innerHTML = '';
    var empty = document.createElement("div");
    empty.className = "trace-empty";
    empty.id = "trace-empty";
    empty.style.display = "flex";
    empty.innerHTML =
      '<div class="trace-empty-inner">' +
      '<span class="cursor-blink">_</span>' +
      '<p>submit a task to begin execution</p></div>';
    trace.appendChild(empty);
  }

  function resetStats() {
    stats = { steps: 0, toolCalls: 0, errors: 0 };
    updateStats(0);
    document.querySelectorAll(".tool-item").forEach(function (el) {
      el.classList.remove("active");
    });
    hideFinalAnswer();
  }

  async function submitTask(task) {
    if (!task) return;
    resetStats();
    clearTrace();
    $("#trace-task").textContent = task;
    setStatus("running");
    var useLlm = $("#use-llm").checked ? "on" : "off";

    var params = { task: task, use_llm: useLlm };
    if (activeConversationId) params.conversation_id = activeConversationId;

    var res = await fetch("/api/runs", {
      method: "POST",
      body: new URLSearchParams(params),
    });
    var data = await res.json();
    activeRunId = data.run_id;
    activeConversationId = data.conversation_id;
    updateConvIndicator();
    connectStream(activeRunId);
  }

  function syncTopBar() {
    var text = $("#topbar-status-text");
    var dot = $("#topbar-dot");
    if (text) text.textContent = $("#state-status").textContent;
    if (dot) {
      dot.className = "status-dot" + ($("#state-status").textContent === "running" ? " active" : "");
    }
  }

  function updateConvIndicator() {
    var indicator = $("#conv-indicator");
    if (!indicator) return;
    if (activeConversationId) {
      indicator.style.display = "flex";
      $("#conv-id").textContent = activeConversationId.slice(0, 6) + "…";
      var tc = countSessionTurns(activeConversationId);
      $("#conv-turns").textContent = tc + (tc === 1 ? " turn" : " turns");
    } else {
      indicator.style.display = "none";
    }
  }

  function groupSessions(rows) {
    var groups = {};
    rows.forEach(function (r) {
      var key = r.conversation_id || "__solo_" + r.run_id;
      if (!groups[key]) groups[key] = [];
      groups[key].push(r);
    });
    var list = [];
    Object.keys(groups).forEach(function (key) {
      var runs = groups[key].sort(function (a, b) { return (a.finished_at || "").localeCompare(b.finished_at || ""); });
      list.push({ conversationId: key.indexOf("__solo_") === 0 ? null : key, runs: runs });
    });
    list.sort(function (a, b) {
      return (b.runs[b.runs.length - 1].finished_at || "").localeCompare(a.runs[a.runs.length - 1].finished_at || "");
    });
    return list;
  }

function countSessionTurns(convId) {
    return sessions.filter(function (s) { return s.conversationId === convId; }).reduce(function (n, s) { return n + s.runs.length; }, 0);
  }

function renderHistory(rows) {
    $("#session-count").textContent = rows.length;
    var list = $("#history-list");
    sessions = groupSessions(rows);

    if (sessions.length === 0) {
      list.innerHTML = '<div class="history-empty">no sessions yet</div>';
      return;
    }

    list.innerHTML = "";
    sessions.forEach(function (session) {
      var turns = session.runs;
      var isSelected = session.conversationId === selectedSessionId;
      var isActive = session.conversationId === activeConversationId;
      var isExpanded = turns.length <= 3 || isActive || isSelected;

      var groupEl = document.createElement("div");
      groupEl.className = "session-group" + (isActive ? " active" : "") + (isSelected && !isActive ? " selected" : "");

      var header = document.createElement("div");
      header.className = "session-header";
      var title = session.conversationId
        ? (session.conversationId.slice(0, 6) + "…")
        : "solo";
      var turnCount = turns.length;
      var turnLabel = turnCount === 1 ? "1 turn" : turnCount + " turns";
      var expandLabel = isExpanded ? "▾" : "▸";
      header.innerHTML =
        '<span class="session-title">' + esc(title) + '</span>' +
        '<span class="session-turns">' + turnLabel + '</span>' +
        '<button class="btn-continue" data-conv-id="' + (session.conversationId || "") + '" title="activate this conversation">&rarr;</button>' +
        '<button class="btn-del-session" title="delete session">×</button>';

      groupEl.appendChild(header);

      if (isExpanded) {
        var turnsEl = document.createElement("div");
        turnsEl.className = "session-turns-list";
        turns.forEach(function (run) {
          var statusLabel = run.cancelled ? "stopped" : (run.success ? "ok" : "fail");
          var elapsed = (run.elapsed || 0).toFixed(1) + "s";
          var model = run.use_llm ? "LLM" : "rule";
          var turnEl = document.createElement("div");
          turnEl.className = "session-turn";
          turnEl.innerHTML =
            '<div class="session-turn-info">' +
            '<div class="session-turn-task">' + esc(run.task.slice(0, 22)) + '</div>' +
            '<div class="session-turn-meta">' +
            statusLabel + " · " + run.steps + "s · " + elapsed + " · " + model +
            '</div></div>' +
            '<button class="btn-del-turn" title="delete turn">×</button>';

          turnEl.addEventListener("click", function () {
            loadRun(run.run_id);
            selectedSessionId = session.conversationId;
            if (session.conversationId && !activeConversationId) {
              activeConversationId = session.conversationId;
              updateConvIndicator();
            }
            refreshHistory();
          });
          turnEl.querySelector(".btn-del-turn").addEventListener("click", function (e) {
            e.stopPropagation();
            deleteHistoryRun(run.run_id);
          });
          turnsEl.appendChild(turnEl);
        });
        groupEl.appendChild(turnsEl);
      }

      header.addEventListener("click", function (e) {
        if (e.target.tagName === "BUTTON") return;
        loadSession(session);
      });

      header.querySelector(".btn-continue").addEventListener("click", function (e) {
        e.stopPropagation();
        if (session.conversationId) {
          activeConversationId = (activeConversationId === session.conversationId) ? null : session.conversationId;
          updateConvIndicator();
          refreshHistory();
          $("#task-input").focus();
        }
      });

      header.querySelector(".btn-del-session").addEventListener("click", function (e) {
        e.stopPropagation();
        Promise.all(turns.map(function (run) {
          return fetch("/api/history/" + run.run_id, { method: "DELETE" });
        })).then(function () {
          refreshHistory();
        });
      });

      list.appendChild(groupEl);
    });
  }

  async function deleteHistoryRun(runId) {
    try {
      await fetch("/api/history/" + runId, { method: "DELETE" });
      refreshHistory();
    } catch (e) {}
  }

  async function refreshHistory() {
    try {
      var res = await fetch("/api/history");
      if (!res.ok) return;
      var data = await res.json();
      renderHistory(Array.isArray(data) ? data : []);
    } catch (e) {
      renderHistory([]);
    }
  }

  async function clearHistory() {
    try {
      await fetch("/api/history", { method: "DELETE" });
      refreshHistory();
    } catch (e) {}
  }

async function refreshMemories() {
    try {
      var res = await fetch("/api/memory");
      if (!res.ok) return;
      var data = await res.json();
      renderMemories(Array.isArray(data) ? data : []);
    } catch (e) {
      renderMemories([]);
    }
  }

function renderMemories(memories) {
    $("#memory-count").textContent = memories.length;
    var list = $("#memory-list");
    if (memories.length === 0) {
      list.innerHTML = '<div class="memory-empty">no memories yet</div>';
      return;
    }
    list.innerHTML = "";
    memories.forEach(function (mem) {
      var item = document.createElement("div");
      item.className = "memory-item" + (mem.success ? " ok" : " fail");
      var statusLabel = mem.success ? "ok" : "fail";
      var ts = mem.timestamp ? new Date(mem.timestamp * 1000).toLocaleString() : "";
      item.innerHTML =
        '<div class="memory-task">' + esc(mem.task) + '</div>' +
        '<div class="memory-result">' + esc((mem.result || "").slice(0, 80)) + '</div>' +
        '<div class="memory-meta">' + statusLabel + " · " + mem.steps + "s · " + ts + '</div>' +
        '<button class="btn-del-memory" title="delete">&times;</button>';
      item.querySelector(".btn-del-memory").addEventListener("click", function (e) {
        e.stopPropagation();
        deleteMemoryItem(mem.key);
      });
      list.appendChild(item);
    });
  }

async function deleteMemoryItem(key) {
    try {
      await fetch("/api/memory/" + key, { method: "DELETE" });
      refreshMemories();
    } catch (e) {}
  }

async function clearAllMemories() {
    try {
      await fetch("/api/memory", { method: "DELETE" });
      refreshMemories();
    } catch (e) {}
  }

  function loadRunEvents(events, cancelled) {
    var lastStepBlock = null;
    events.forEach(function (ev) {
      var d = ev.data;
      if (ev.type === "step_thought") {
        stats.steps = Math.max(stats.steps, d.step);
        lastStepBlock = appendTraceStep(d.step, d.thought);
      } else if (ev.type === "tool_call") {
        stats.toolCalls++;
        if (lastStepBlock) appendToolCall(lastStepBlock, d.tool_name, d.tool_args);
      } else if (ev.type === "tool_result") {
        if (lastStepBlock) appendToolResult(lastStepBlock, d);
        if (!d.success) stats.errors++;
      } else if (ev.type === "step_end") {
        if (lastStepBlock && d.answer) appendAnswer(lastStepBlock, d.answer);
      } else if (ev.type === "agent_done") {
        showFinalAnswer(d.success && !cancelled, d.result, cancelled);
        var lastBlock = document.querySelector(".trace-step-block:last-child");
        if (lastBlock && d.success) lastBlock.classList.add("step-final");
        if (lastBlock && !d.success && !cancelled) lastBlock.classList.add("step-error");
      }
    });
    return lastStepBlock;
  }

  async function loadRun(runId) {
    var res = await fetch("/api/runs/" + runId);
    var data = await res.json();
    if (data.error) return;

    resetStats();
    clearTrace();
    $("#trace-task").textContent = data.task;
    var cancelled = data.cancelled;
    setStatus(cancelled ? "cancelled" : (data.done ? "done" : "running"));

    loadRunEvents(data.events, cancelled);
    updateStats(data.elapsed || 0);
  }

  async function loadSession(session) {
    selectedSessionId = session.conversationId;
    if (session.conversationId) {
      activeConversationId = session.conversationId;
      updateConvIndicator();
    }
    resetStats();
    clearTrace();

    var turns = session.runs;
    var latest = turns[turns.length - 1];
    setStatus(latest.cancelled ? "cancelled" : "done");
    $("#trace-task").textContent = session.conversationId
      ? "session " + session.conversationId.slice(0, 6) + "… · " + turns.length + " turns"
      : turns.length + " runs";

    for (var idx = 0; idx < turns.length; idx++) {
      var run = turns[idx];
      var res = await fetch("/api/runs/" + run.run_id);
      var data = await res.json();
      if (data.error) continue;

      if (idx > 0) {
        var sep = document.createElement("div");
        sep.className = "turn-separator";
        sep.innerHTML = '<span>turn ' + (idx + 1) + '</span>';
        $("#trace").appendChild(sep);
      }

      var turnHeader = document.createElement("div");
      turnHeader.className = "turn-header";
      var statusLabel = run.cancelled ? "stopped" : (run.success ? "ok" : "fail");
      var elapsed = (run.elapsed || 0).toFixed(1) + "s";
      var model = run.use_llm ? "LLM" : "rule";
      turnHeader.innerHTML =
        '<span class="turn-header-label">TURN ' + (idx + 1) + '</span>' +
        '<span class="turn-header-task">' + esc(run.task.slice(0, 40)) + '</span>' +
        '<span class="turn-header-meta">' + statusLabel + " · " + run.steps + "s · " + elapsed + " · " + model + '</span>';
      $("#trace").appendChild(turnHeader);

      loadRunEvents(data.events, run.cancelled);
    }

    updateStats(latest.elapsed || 0);
    refreshHistory();
  }

  var ruleMatches = [];
try {
  ruleMatches = JSON.parse(document.getElementById("rule-matches").textContent);
} catch (_) {}

function updateModeHint(useLlm) {
  var label = $("#mode-hint-label");
  var text = $("#mode-hint-text");
  if (!label || !text) return;
  if (useLlm) {
    label.textContent = "free-form";
    text.textContent = "describe any task";
  } else {
    label.textContent = "rule-based";
    text.textContent = ruleMatches.length > 0
      ? 'try: "' + ruleMatches.join('", "') + '"'
      : "no rules configured";
  }
}

document.addEventListener("DOMContentLoaded", function () {
    $("#task-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var input = $("#task-input");
      var task = input.value.trim();
      if (!task) return;
      input.value = "";
      submitTask(task);
    });

    $("#task-input").addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        e.target.value = "";
        e.target.blur();
      }
    });

    var cancelBtn = $("#btn-cancel");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        cancelRun();
      });
    }

    var clearHistoryBtn = $("#btn-clear-history");
    if (clearHistoryBtn) {
      clearHistoryBtn.addEventListener("click", function () {
        clearHistory();
      });
    }

    var convClearBtn = $("#conv-clear");
    if (convClearBtn) {
      convClearBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        activeConversationId = null;
        selectedSessionId = null;
        updateConvIndicator();
        refreshHistory();
      });
    }

    var clearMemoryBtn = $("#btn-clear-memory");
    if (clearMemoryBtn) {
      clearMemoryBtn.addEventListener("click", function () {
        clearAllMemories();
      });
    }

    $("#use-llm").addEventListener("change", function () {
      $("#mode-text").textContent = this.checked ? "glm-5.2" : "rule-based";
      $("#state-model").textContent = this.checked ? "glm-5.2" : "rule-based";
      $("#agent-type").textContent = this.checked ? "LLM" : "rule-based";
      updateModeHint(this.checked);
    });

    updateModeHint($("#use-llm").checked);
    refreshHistory();
    refreshMemories();
    updateStats(0);
  });

  window.__agent = { submitTask: submitTask, loadRun: loadRun, loadSession: loadSession };
})();
