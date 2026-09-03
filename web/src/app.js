(function () {
  "use strict";

  var sessions = [];
  var activeRunId = null;
  var eventSource = null;
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
    var title = $("#trace-title");
    if (title) {
      title.textContent = s === "idle" ? "// idle" : "// " + s;
      title.className = "trace-title" + (s === "running" ? " active" : "");
    }
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

    var toolNameEl = document.querySelector('.tool-item .tool-name[style]');
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
    var resBlock = document.createElement("div");
    resBlock.className = "trace-result-block" + (data.error ? " error" : "");
    var tag = data.error ? "ERR" : "OK";
    resBlock.innerHTML =
      '<span class="trace-result-tag">[' + tag + ']</span>' +
      esc((data.output || (data.error || "")).slice(0, 300));
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
    resBlock.innerHTML = '<span class="trace-result-tag">[ERR]</span>' + esc(error);
    block.appendChild(resBlock);
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
        setStatus("idle");
        $("#footer-cursor").textContent = "ready";
        return;
      }

      if (msg.type === "agent_start") {
        setStatus("running");
        $("#footer-cursor").textContent = "executing";
        return;
      }

      if (msg.type === "step_thought") {
        stats.steps = Math.max(stats.steps, msg.data.step);
        var block = appendTraceStep(msg.data.step, msg.data.thought);
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

      if (msg.type === "agent_done") {
        setStatus(msg.data.success ? "done" : "failed");
        $("#footer-cursor").textContent = msg.data.success ? "completed" : "failed";
        var lastBlock = document.querySelector(".trace-step-block:last-child");
        if (lastBlock && msg.data.success) lastBlock.classList.add("step-final");
        if (lastBlock && !msg.data.success) lastBlock.classList.add("step-error");

        sessions.unshift({
          id: activeRunId,
          task: msg.data.task || "task",
          success: msg.data.success,
          steps: msg.data.steps,
          time: performance.now(),
        });
        updateHistory();
        return;
      }

      if (msg.type === "agent_error") {
        setStatus("failed");
        $("#footer-cursor").textContent = "error";
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
  }

  async function submitTask(task) {
    if (!task) return;
    resetStats();
    clearTrace();
    $("#trace-task").textContent = task;
    setStatus("running");
    var useLlm = $("#use-llm").checked ? "on" : "off";

    var res = await fetch("/api/runs", {
      method: "POST",
      body: new URLSearchParams({ task: task, use_llm: useLlm }),
    });
    var data = await res.json();
    activeRunId = data.run_id;
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

  function updateHistory() {
    $("#session-count").textContent = sessions.length;
    var list = $("#history-list");
    if (sessions.length === 0) {
      list.innerHTML = '<div class="history-empty">no sessions yet</div>';
      return;
    }
    list.innerHTML = "";
    sessions.forEach(function (s) {
      var item = document.createElement("div");
      item.className = "history-item";
      item.innerHTML =
        '<div class="h-task">' + esc(s.task.slice(0, 30)) + "</div>" +
        '<div class="h-meta">' + (s.success ? "ok" : "fail") +
        " · " + s.steps + " steps</div>";
      item.addEventListener("click", function () {
        loadRun(s.id);
      });
      list.appendChild(item);
    });
  }

  async function loadRun(runId) {
    var res = await fetch("/api/runs/" + runId);
    var data = await res.json();
    if (data.error) return;

    resetStats();
    clearTrace();
    $("#trace-task").textContent = data.task;
    setStatus(data.done ? "done" : "running");

    data.events.forEach(function (ev) {
      var d = ev.data;
      if (ev.type === "step_thought") {
        stats.steps = Math.max(stats.steps, d.step);
        var block = appendTraceStep(d.step, d.thought);
      } else if (ev.type === "tool_call") {
        stats.toolCalls++;
        var el = document.querySelector('[data-step="' + d.step + '"]');
        if (el) appendToolCall(el, d.tool_name, d.tool_args);
      } else if (ev.type === "tool_result") {
        var el2 = document.querySelector('[data-step="' + d.step + '"]');
        if (el2) appendToolResult(el2, d);
        if (!d.success) stats.errors++;
      } else if (ev.type === "step_end") {
        var el3 = document.querySelector('[data-step="' + d.step + '"]');
        if (el3 && d.answer) appendAnswer(el3, d.answer);
      } else if (ev.type === "agent_done") {
        var lastBlock = document.querySelector(".trace-step-block:last-child");
        if (lastBlock && d.success) lastBlock.classList.add("step-final");
        if (lastBlock && !d.success) lastBlock.classList.add("step-error");
      }
    });
    updateStats(data.elapsed || 0);
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

    $("#use-llm").addEventListener("change", function () {
      $("#mode-text").textContent = this.checked ? "glm-5.2" : "rule-based";
      $("#state-model").textContent = this.checked ? "glm-5.2" : "rule-based";
      $("#agent-type").textContent = this.checked ? "LLM" : "rule-based";
    });

    updateHistory();
    updateStats(0);
  });

  window.__agent = { submitTask: submitTask, loadRun: loadRun };
})();
