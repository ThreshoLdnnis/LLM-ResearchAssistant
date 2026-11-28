const form = document.getElementById("upload-form");
const picker = document.getElementById("pdf-files");
const manual = document.getElementById("manual-fields");
const submitButton = document.getElementById("upload-submit");
const progress = document.getElementById("upload-progress");
const results = document.getElementById("upload-results");

function toggleManual() {
  const batch = picker.files.length > 1;
  manual.hidden = batch;
  for (const field of manual.querySelectorAll("input, select")) field.disabled = batch;
}
picker.addEventListener("change", toggleManual);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const files = Array.from(picker.files);
  if (!files.length || submitButton.disabled) return;
  const fields = new FormData(form);
  fields.delete("file");
  picker.disabled = submitButton.disabled = true;
  results.replaceChildren();
  results.hidden = progress.hidden = false;
  let succeeded = 0;
  try {
    for (const [index, file] of files.entries()) {
      progress.textContent = `正在处理 ${index + 1}/${files.length} · ${file.name}`;
      const payload = new FormData();
      for (const [key, value] of fields) payload.append(key, value);
      payload.append("file", file);
      const row = document.createElement("li");
      try {
        const response = await fetch(form.action, {method: "POST", body: payload, headers: {Accept: "application/json"}});
        if (response.status === 413) throw new Error("单份文件超过上传上限");
        const body = await response.json();
        if (!response.ok || body.errors.length) throw new Error(body.errors.join("；"));
        row.textContent = body.messages.join("；");
        succeeded++;
      } catch (error) {
        row.textContent = `${file.name} · 入库失败 · ${error.message}`;
      }
      results.append(row);
    }
    progress.textContent = `完成 · 已入库 ${succeeded} 份，失败 ${files.length - succeeded} 份`;
    if (succeeded) {
      document.getElementById("open-library").hidden = false;
      const response = await fetch("/import", {cache: "no-store"});
      if (!response.ok) throw new Error();
      const page = new DOMParser().parseFromString(await response.text(), "text/html");
      for (const selector of [".rail .count", ".rail-docs", ".rail-foot"]) {
        document.querySelector(selector).replaceWith(page.querySelector(selector));
      }
    }
    if (succeeded === files.length) form.reset();
  } catch {
    progress.textContent += "。请刷新页面查看文档库。";
  } finally {
    picker.disabled = submitButton.disabled = false;
    toggleManual();
  }
});
