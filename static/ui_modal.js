/* ============================================================
 * 公共网页弹窗模块（替代浏览器 alert/confirm）
 * 样式与富文本编辑器弹窗（rt-modal）一致
 * 用法：
 *   uiModal.alert("提示文字");
 *   uiModal.alert("提示文字", function(){ ... });
 *   uiModal.alert("提示文字", "标题", function(){ ... });
 *   uiModal.alert({ message:"...", title:"提示", maskClose:false, onOk:function(){...} });
 *   uiModal.confirm("确定执行吗？", function(){ ... });
 *   uiModal.confirm({ title:"确认", message:"...", okText:"确定", cancelText:"取消", maskClose:false, onOk:function(){...} });
 *   uiModal.show({ title, message, maskClose, buttons:[{text,cls,onClick},...] });   // 完全自定义
 *   uiModal.close();   // 手动关闭
 * ============================================================ */
(function(){
    if(window.uiModal) return;

    var st = document.createElement("style");
    st.textContent = [
        ".rt-modal{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.4);z-index:9999;align-items:center;justify-content:center;}",
        ".rt-modal-card{background:#fff;border-radius:8px;padding:24px;width:420px;max-width:92vw;max-height:90vh;overflow-y:auto;box-shadow:0 4px 20px rgba(0,0,0,.2);}",
        ".rt-modal-card h3{margin:0 0 14px;font-size:16px;}",
        "#uiModalBody{font-size:14px;color:#333;line-height:1.7;word-break:break-word;}",
        ".rt-modal-btns{margin-top:16px;text-align:right;display:flex;justify-content:flex-end;align-items:center;gap:8px;}"
    ].join("\n");
    document.head.appendChild(st);

    var MODAL_ID = "uiModalBox";

    function esc(s){
        return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }
    function ensure(){
        if(document.getElementById(MODAL_ID)) return;
        var m = document.createElement("div");
        m.className = "rt-modal";
        m.id = MODAL_ID;
        m.innerHTML =
            '<div class="rt-modal-card">' +
            '    <h3 id="uiModalTitle">提示</h3>' +
            '    <div id="uiModalBody"></div>' +
            '    <div class="rt-modal-btns" id="uiModalBtns"></div>' +
            '</div>';
        document.body.appendChild(m);
        // 遮罩点击：仅在允许时关闭（data-mask-close=0 时忽略遮罩点击）
        m.addEventListener("click", function(e){
            if(e.target === m && m.getAttribute("data-mask-close") !== "0") close();
        });
    }
    function close(){
        var m = document.getElementById(MODAL_ID);
        if(m) m.style.display = "none";
    }
    function open(opts){
        ensure();
        var m = document.getElementById(MODAL_ID);
        document.getElementById("uiModalTitle").textContent = opts.title || "提示";
        document.getElementById("uiModalBody").innerHTML = opts.bodyHtml || "";
        var btnsDom = document.getElementById("uiModalBtns");
        var html = "";
        (opts.buttons || []).forEach(function(b, i){
            html += '<button type="button" class="' + (b.cls || "btn") + '" data-ui-btn="' + i + '">' + esc(b.text) + '</button>';
        });
        btnsDom.innerHTML = html;
        Array.prototype.forEach.call(btnsDom.querySelectorAll("[data-ui-btn]"), function(btn, i){
            btn.onclick = (opts.buttons || [])[i].onClick || close;
        });
        m.setAttribute("data-mask-close", opts.maskClose === false ? "0" : "1");
        m.style.display = "flex";
    }

    window.uiModal = {
        close: close,
        show: function(opts){
            open({
                title: opts.title || "提示",
                bodyHtml: '<div>' + esc(opts.message == null ? "" : opts.message) + '</div>',
                maskClose: opts.maskClose,
                buttons: opts.buttons || []
            });
        },
        alert: function(text, title, cb){
            var o = {};
            if(typeof text === "object"){
                o = text;
            }else{
                o.message = text;
                if(typeof title === "function"){ o.onOk = title; o.title = "提示"; }
                else{ o.title = title || "提示"; o.onOk = cb; }
            }
            open({
                title: o.title || "提示",
                bodyHtml: '<div>' + esc(o.message) + '</div>',
                maskClose: o.maskClose !== false,
                buttons: [{
                    text: o.okText || "知道了",
                    cls: "btn",
                    onClick: function(){ close(); if(o.onOk) o.onOk(); }
                }]
            });
        },
        confirm: function(opts, onOk){
            if(typeof opts === "string"){ opts = { title: "确认", message: opts, onOk: onOk }; }
            open({
                title: opts.title || "确认",
                bodyHtml: '<div>' + esc(opts.message) + '</div>',
                maskClose: opts.maskClose !== false,
                buttons: [
                    { text: opts.cancelText || "取消", cls: "btn btn-gray", onClick: close },
                    { text: opts.okText || "确定", cls: "btn", onClick: function(){ close(); if(opts.onOk) opts.onOk(); } }
                ]
            });
        }
    };
})();