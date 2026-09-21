/* ============================================================
 * 富文本编辑器公共模块
 * 所有需要富文本的界面统一调用 window.mountRichEditor(containerId, options)
 * 扩充/修改工具栏功能只需改本文件，各页面自动生效。
 *
 * 用法：
 *   let rt = mountRichEditor("contentEditor", {height:160, content:""});
 *   rt.getContent()  // 取 HTML
 *   rt.getText()     // 取纯文本（用于判空）
 *   rt.setContent(html)
 *
 * 说明：
 *   - 工具栏按“分组”组织，每组是一个整体（.rt-tb-section），
 *     窗口变窄时整组换行，不会拆散到两行。
 *   - 撤销/重做为自定义历史栈，用 MutationObserver 自动记录
 *     所有内容变化（包括直接改样式的首行缩进），Ctrl+Z / Ctrl+Y
 *     与按钮同样生效。
 *   - 首行缩进：作用于光标所在段落，再次点击可取消。
 * ============================================================ */
(function(){
    // 注入编辑器样式（只注入一次）
    if(!document.getElementById("rtEditorStyle")){
        var st = document.createElement("style");
        st.id = "rtEditorStyle";
        st.textContent = [
            ".rt-editor-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:6px 8px;background:#f7f7f7;border:1px solid #eee;border-radius:4px;margin-bottom:8px;}",
            /* 分组整体：内部不换行，整组随容器换行 */
            ".rt-editor-toolbar .rt-tb-section{display:inline-flex;align-items:center;gap:4px;flex-shrink:0;}",
            ".rt-editor-toolbar .tb-group-label{font-size:12px;color:#888;white-space:nowrap;margin-right:2px;}",
            ".rt-editor-toolbar .tb-btn{background:#fff;border:1px solid #ddd;border-radius:4px;padding:2px 9px;cursor:pointer;font-size:13px;line-height:1.7;color:#333;min-width:24px;text-align:center;white-space:nowrap;flex-shrink:0;}",
            ".rt-editor-toolbar .tb-btn:hover{background:#f0f4ff;color:#1f4e99;border-color:#1f4e99;}",
            ".rt-editor-toolbar .tb-btn.active{background:#1f4e99;color:#fff;border-color:#1f4e99;}",
            ".rt-editor-toolbar .tb-sep{width:1px;height:18px;background:#ddd;align-self:center;flex-shrink:0;}",
            ".rt-editor-toolbar .rt-right-group{margin-left:auto;display:inline-flex;align-items:center;gap:4px;flex-shrink:0;}",
            ".rt-editor-toolbar .rt-title-flat{display:none;align-items:center;gap:4px;flex-shrink:0;}",
            ".rt-editor-toolbar .rt-tb-section.rt-title-expanded{flex-basis:100%;}",
            ".rt-tb-group{position:relative;display:inline-block;flex-shrink:0;}",
            ".rt-tb-group:hover .rt-tb-dropdown{display:block;}",
            ".rt-tb-dropdown{display:none;position:absolute;left:0;top:100%;z-index:999;min-width:130px;padding-top:4px;background:transparent;}",
            ".rt-tb-dropdown::before{content:'';position:absolute;top:0;left:0;right:0;height:4px;}",
            ".rt-tb-dropdown .rt-tb-menu{background:#fff;border:1px solid #ddd;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.15);padding:4px 0;max-height:280px;overflow-y:auto;}",
            ".rt-tb-dropdown button{display:block;width:100%;border:none;background:none;text-align:left;padding:7px 12px;cursor:pointer;font-size:13px;color:#333;white-space:nowrap;}",
            ".rt-tb-dropdown button:hover{background:#f0f4ff;color:#1f4e99;}",
            ".rt-tb-dropdown button.active{background:#1f4e99;color:#fff;}",
            ".rt-tb-dropdown .rt-color-item{display:flex;align-items:center;gap:8px;}",
            ".rt-tb-dropdown .rt-color-dot{width:14px;height:14px;border-radius:50%;border:1px solid #ddd;display:inline-block;flex-shrink:0;}",
            /* 编辑框 */
            ".rt-editor-box{min-height:160px;border:1px solid #ccc;border-radius:4px;padding:8px;background:#fff;line-height:1.8;outline:none;overflow-wrap:break-word;}",
            ".rt-editor-box:focus{border-color:#1f4e99;}",
            ".rt-editor-box img{max-width:100%;}",
            ".rt-editor-box a{color:#1f4e99;}",
            ".rt-editor-box h1,.rt-editor-box h2,.rt-editor-box h3,.rt-editor-box h4,.rt-editor-box h5{margin:8px 0 4px;line-height:1.4;}",
            ".rt-editor-box h1{font-size:24px;}",
            ".rt-editor-box h2{font-size:21px;}",
            ".rt-editor-box h3{font-size:18px;}",
            ".rt-editor-box h4{font-size:16px;}",
            ".rt-editor-box h5{font-size:14px;}",
            ".rt-editor-box p{margin:4px 0;}",
            /* 列表：序号显示在框内，缩进紧凑（光标不跳） */
            ".rt-editor-box ol,.rt-editor-box ul{padding-left:1.8em!important;margin:4px 0!important;list-style-position:outside!important;}",
            ".rt-editor-box ol{list-style-type:decimal!important;}",
            ".rt-editor-box ul{list-style-type:disc!important;}",
            ".rt-editor-box li{margin:2px 0!important;}",
            ".rt-editor-box blockquote{margin:6px 0;padding:4px 12px;border-left:3px solid #ccc;color:#555;background:#f9f9f9;}",
            ".rt-editor-box pre{background:#f5f5f5;padding:10px;border-radius:4px;border:1px solid #eee;overflow-x:auto;font-size:13px;}",
            ".rt-editor-box table{border-collapse:collapse;width:100%;margin:8px 0;}",
            ".rt-editor-box table td,.rt-editor-box table th{border:1px solid #ccc;padding:6px;}",
            ".rt-editor-box font[size='1']{font-size:12px;}",
            ".rt-editor-box font[size='2']{font-size:14px;}",
            ".rt-editor-box font[size='3']{font-size:16px;}",
            ".rt-editor-box font[size='4']{font-size:18px;}",
            ".rt-editor-box font[size='5']{font-size:24px;}",
            ".rt-editor-box font[size='6']{font-size:32px;}",
            ".rt-editor-box font[size='7']{font-size:48px;}",
            /* 悬浮弹窗（样式与账号管理弹窗一致） */
            ".rt-modal{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.4);z-index:9999;align-items:center;justify-content:center;}",
            ".rt-modal-card{background:#fff;border-radius:8px;padding:24px;width:420px;max-width:92vw;max-height:90vh;overflow-y:auto;box-shadow:0 4px 20px rgba(0,0,0,.2);}",
            ".rt-modal-card h3{margin:0 0 14px;font-size:16px;}",
            ".rt-modal-field{margin-bottom:12px;}",
            ".rt-modal-field label{display:block;margin-bottom:4px;font-size:13px;color:#333;}",
            ".rt-modal-field input[type='text'],.rt-modal-field input[type='url']{width:100%;padding:8px;border:1px solid #ccc;border-radius:4px;box-sizing:border-box;font-size:13px;}",
            ".rt-modal-field input:focus{border-color:#1f4e99;outline:none;}",
            ".rt-modal-field input[type='file']{width:100%;padding:6px;border:1px solid #ccc;border-radius:4px;box-sizing:border-box;font-size:13px;background:#fff;}",
            ".rt-modal-tip{color:#888;font-size:12px;margin-top:4px;}",
            ".rt-modal-error{color:#b71c1c;font-size:12px;margin-bottom:8px;display:none;}",
            ".rt-modal-btns{margin-top:16px;text-align:right;display:flex;justify-content:flex-end;align-items:center;gap:8px;}",
            ".rt-modal-btns .btn-del{margin-right:auto;background:none;border:1px solid #e0e0e0;color:#666;border-radius:4px;padding:6px 14px;cursor:pointer;font-size:13px;}",
            ".rt-modal-btns .btn-del:hover{color:#b71c1c;border-color:#b71c1c;}"
        ].join("\n");
        document.head.appendChild(st);
    }

    function exec(cmd){
        document.execCommand(cmd, false, null);
    }

    // HTML 转义（防注入）
    function escHtml(s){
        return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }
    // hex color to "rgb(r, g, b)" string (match queryCommandValue("foreColor"))
    function hexToRgbStr(hex){
        hex = String(hex || "").replace("#", "");
        if(hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
        var r = parseInt(hex.substr(0,2), 16);
        var g = parseInt(hex.substr(2,2), 16);
        var b = parseInt(hex.substr(4,2), 16);
        return "rgb(" + r + ", " + g + ", " + b + ")";
    }

    // ========== 表格操作 ==========
    function getTable(editor){
        var sel = window.getSelection();
        if(!sel || !sel.rangeCount) return null;
        var node = sel.anchorNode;
        if(node && node.nodeType === 3) node = node.parentNode;
        while(node && node !== editor && node !== document.body){
            if(node.tagName === "TABLE") return node;
            node = node.parentNode;
        }
        return null;
    }
    function getRow(editor){
        var sel = window.getSelection();
        if(!sel || !sel.rangeCount) return null;
        var node = sel.anchorNode;
        if(node && node.nodeType === 3) node = node.parentNode;
        while(node && node !== editor && node !== document.body){
            if(node.tagName === "TR") return node;
            node = node.parentNode;
        }
        return null;
    }
    function getCell(editor){
        var sel = window.getSelection();
        if(!sel || !sel.rangeCount) return null;
        var node = sel.anchorNode;
        if(node && node.nodeType === 3) node = node.parentNode;
        while(node && node !== editor && node !== document.body){
            if(node.tagName === "TD" || node.tagName === "TH") return node;
            node = node.parentNode;
        }
        return null;
    }
    function insertTable(editor){
        var html = '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;margin:8px 0;"><tr><td>&nbsp;</td><td>&nbsp;</td></tr><tr><td>&nbsp;</td><td>&nbsp;</td></tr></table>';
        document.execCommand("insertHTML", false, html);
        editor.focus();
    }
    function addRow(editor){
        var tb = getTable(editor);
        if(!tb){ showRtMsg("请先点击表格内的任意位置"); return; }
        var cols = tb.rows[0] ? tb.rows[0].cells.length : 2;
        var row = tb.insertRow(-1);
        for(var i=0;i<cols;i++){
            var cell = row.insertCell(-1);
            cell.innerHTML = "&nbsp;";
            cell.style.border = "1px solid #ccc";
            cell.style.padding = "6px";
        }
        tb.style.borderCollapse = "collapse";
        tb.setAttribute("border","1");
        editor.focus();
    }
    function addCol(editor){
        var tb = getTable(editor);
        if(!tb){ showRtMsg("请先点击表格内的任意位置"); return; }
        for(var i=0;i<tb.rows.length;i++){
            var cell = tb.rows[i].insertCell(-1);
            cell.innerHTML = "&nbsp;";
            cell.style.border = "1px solid #ccc";
            cell.style.padding = "6px";
        }
        tb.style.borderCollapse = "collapse";
        tb.setAttribute("border","1");
        editor.focus();
    }
    function delRow(editor){
        var tb = getTable(editor);
        if(!tb){ showRtMsg("请先点击表格内的任意位置"); return; }
        var tr = getRow(editor);
        if(!tr){ showRtMsg("请先点击要删除的那一行"); return; }
        if(tb.rows.length <= 1){ showRtMsg("表格至少保留一行"); return; }
        tb.deleteRow(tr.rowIndex);
        editor.focus();
    }
    function delCol(editor){
        var tb = getTable(editor);
        if(!tb){ showRtMsg("请先点击表格内的任意位置"); return; }
        var td = getCell(editor);
        if(!td){ showRtMsg("请先点击要删除的那一列中的任意单元格"); return; }
        if(tb.rows[0].cells.length <= 1){ showRtMsg("表格至少保留一列"); return; }
        var idx = td.cellIndex;
        for(var i=0;i<tb.rows.length;i++){
            if(tb.rows[i].cells[idx]) tb.rows[i].deleteCell(idx);
        }
        editor.focus();
    }
    function delTable(editor){
        var tb = getTable(editor);
        if(!tb){ showRtMsg("请先点击表格内的任意位置"); return; }
        showRtConfirm("确定删除该表格吗？", function(){
            tb.remove();
            editor.focus();
        });
    }

    // ========== 标题 / 颜色 / 字号 / 缩进 / 列表 ==========
    function setHeading(editor, tag){
        document.execCommand("formatBlock", false, "<" + tag + ">");
        editor.focus();
    }
    function setColor(editor, color){
        if(color){
            document.execCommand("styleWithCSS", false, true);
            document.execCommand("foreColor", false, color);
        }else{
            document.execCommand("styleWithCSS", false, false);
            document.execCommand("removeFormat", false, null);
        }
        editor.focus();
    }
    function setFontSize(editor, n){
        document.execCommand("styleWithCSS", false, true);
        document.execCommand("fontSize", false, n);
        editor.focus();
    }
    function setIndent(editor, mode){
        if(mode === "in"){ document.execCommand("indent", false, null); editor.focus(); return; }
        if(mode === "out"){ document.execCommand("outdent", false, null); editor.focus(); return; }
        if(mode === "first"){
            // 只作用于光标所在段落，再次点击可取消
            var sel = window.getSelection();
            if(!sel || !sel.rangeCount){ return; }
            var node = sel.anchorNode;
            if(node && node.nodeType === 3) node = node.parentNode;
            var block = node ? node.closest("p,div,h1,h2,h3,h4,h5,pre,blockquote,li") : null;
            // 关键：排除编辑器容器自身，避免把整个编辑框（所有行）一起缩进
            if(!block || block === editor || !editor.contains(block)){
                showRtMsg("请先将光标定位到具体段落内容中，再设置首行缩进");
                editor.focus();
                return;
            }
            var cur = block.style.textIndent || "";
            if(cur === "2em" || cur === "2em "){
                block.style.textIndent = "";
            }else{
                block.style.textIndent = "2em";
            }
            block.style.paddingLeft = "";
            editor.focus();
        }
    }
    // 列表：原生列表（可再次点击取消列表）
    function toggleList(editor, type){
        if(type === "ol") document.execCommand("insertOrderedList", false, null);
        else document.execCommand("insertUnorderedList", false, null);
        editor.focus();
    }

    // ========== 悬浮弹窗（通用） ==========
    var rtModal = null;
    function ensureModal(){
        if(rtModal) return;
        var m = document.createElement("div");
        m.className = "rt-modal";
        m.id = "rtInsertModal";
        m.innerHTML =
            '<div class="rt-modal-card">' +
            '    <h3 id="rtModalTitle">插入</h3>' +
            '    <div id="rtModalFields"></div>' +
            '    <div class="rt-modal-error" id="rtModalError"></div>' +
            '    <div class="rt-modal-btns">' +
            '        <button type="button" class="btn-del" id="rtModalDel" style="display:none;">删除</button>' +
            '        <button type="button" class="btn btn-gray" id="rtModalCancel">取消</button>' +
            '        <button type="button" class="btn" id="rtModalOk">确定</button>' +
            '    </div>' +
            '</div>';
        document.body.appendChild(m);
        m.addEventListener("click", function(e){
            if(e.target === m) closeRtModal();
        });
        document.getElementById("rtModalCancel").addEventListener("click", closeRtModal);
        rtModal = m;
    }
    function closeRtModal(){
        if(rtModal) rtModal.style.display = "none";
    }
    function showRtModal(opts){
        ensureModal();
        var m = document.getElementById("rtInsertModal");
        document.getElementById("rtModalTitle").textContent = opts.title || "插入";
        var fieldsHtml = "";
        (opts.fields || []).forEach(function(f){
            if(f.type === "file"){
                fieldsHtml += '<div class="rt-modal-field"><label>' + f.label + '</label><input type="file" id="' + f.id + '" accept="' + (f.accept || "") + '"></div>';
            }else if(f.type === "checkbox"){
                fieldsHtml += '<div class="rt-modal-field"><label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:14px;color:#333;"><input type="checkbox" id="' + f.id + '"' + (f.checked ? ' checked' : '') + ' style="width:16px;height:16px;">' + f.label + '</label>' + (f.tip ? '<div class="rt-modal-tip">' + f.tip + '</div>' : '') + '</div>';
            }else{
                fieldsHtml += '<div class="rt-modal-field"><label>' + f.label + '</label><input type="text" id="' + f.id + '" value="' + escHtml(f.value || "") + '" placeholder="' + escHtml(f.placeholder || "") + '"></div>';
            }
        });
        document.getElementById("rtModalFields").innerHTML = fieldsHtml;
        var err = document.getElementById("rtModalError");
        err.style.display = "none";
        err.textContent = "";
        var okBtn = document.getElementById("rtModalOk");
        okBtn.textContent = opts.okText || "确定";
        var delBtn = document.getElementById("rtModalDel");
        if(opts.showDelete){
            delBtn.style.display = "block";
            delBtn.onclick = function(){
                if(opts.onDelete) opts.onDelete();
                closeRtModal();
            };
        }else{
            delBtn.style.display = "none";
            delBtn.onclick = null;
        }
        okBtn.onclick = function(){
            var vals = {};
            (opts.fields || []).forEach(function(f){
                var el = document.getElementById(f.id);
                if(el) vals[f.id] = (f.type === "file") ? (el.files && el.files[0] ? el.files[0] : null) : (f.type === "checkbox") ? el.checked : el.value;
            });
            var ret = opts.onOk(vals);
            if(ret === true){
                closeRtModal();
            }else if(ret && ret.ok === false){
                err.textContent = ret.msg || "请检查输入";
                err.style.display = "block";
            }
        };
        m.style.display = "flex";
    }
    // 通用提示弹窗（单按钮）
    function showRtMsg(text, title){
        ensureModal();
        var m = document.getElementById("rtInsertModal");
        document.getElementById("rtModalTitle").textContent = title || "提示";
        document.getElementById("rtModalFields").innerHTML = '<div style="font-size:14px;color:#333;line-height:1.6;">' + escHtml(text) + '</div>';
        var err = document.getElementById("rtModalError");
        err.style.display = "none";
        document.getElementById("rtModalOk").textContent = "知道了";
        document.getElementById("rtModalDel").style.display = "none";
        document.getElementById("rtModalOk").onclick = closeRtModal;
        document.getElementById("rtModalCancel").style.display = "none";
        m.style.display = "flex";
    }
    // 确认弹窗（确定/取消）
    function showRtConfirm(text, onOk){
        ensureModal();
        var m = document.getElementById("rtInsertModal");
        document.getElementById("rtModalTitle").textContent = "确认";
        document.getElementById("rtModalFields").innerHTML = '<div style="font-size:14px;color:#333;line-height:1.6;">' + escHtml(text) + '</div>';
        var err = document.getElementById("rtModalError");
        err.style.display = "none";
        document.getElementById("rtModalOk").textContent = "确定";
        document.getElementById("rtModalDel").style.display = "none";
        document.getElementById("rtModalCancel").style.display = "";
        document.getElementById("rtModalOk").onclick = function(){ closeRtModal(); if(onOk) onOk(); };
        m.style.display = "flex";
    }

    // ========== 插入：链接 / 图片（悬浮弹窗） ==========

    // 插入或修改链接（existingA 存在时为修改模式）
    function insertLinkFlow(editor, existingA){
        showRtModal({
            title: existingA ? "修改链接" : "插入链接",
            fields: [
                { id: "rtLnkUrl", label: "链接地址（URL）", value: existingA ? existingA.href : "", placeholder: "https://..." },
                { id: "rtLnkText", label: "显示文字（留空则显示地址）", value: existingA ? existingA.innerText : "", placeholder: "点击后跳转显示的文字" }
            ],
            okText: "确定",
            showDelete: !!existingA,
            onDelete: function(){ existingA.remove(); editor.focus(); },
            onOk: function(vals){
                var url = (vals.rtLnkUrl || "").trim();
                if(!url){ return { ok: false, msg: "链接地址不能为空" }; }
                var text = (vals.rtLnkText || "").trim() || url;
                if(existingA){
                    existingA.href = url;
                    existingA.innerText = text;
                    editor.focus();
                }else{
                    document.execCommand("insertHTML", false,
                        '<a href="' + escHtml(url) + '" target="_blank" rel="noopener">' + escHtml(text) + '</a>');
                    editor.focus();
                }
                return true;
            }
        });
    }

    // 插入图片：URL 或本地文件
    function insertImageFlow(editor){
        showRtModal({
            title: "插入图片",
            fields: [
                { id: "rtImgUrl", label: "图片地址（URL，与本地文件二选一）", value: "", placeholder: "https://..." },
                { id: "rtImgFile", label: "或选择本地图片文件", type: "file", accept: "image/*" }
            ],
            okText: "插入",
            onOk: function(vals){
                var file = vals.rtImgFile;
                var url = (vals.rtImgUrl || "").trim();
                if(file && file.size){
                    if(file.size > 2 * 1024 * 1024){
                        return { ok: false, msg: "图片超过 2MB，请压缩后重试或改用 URL" };
                    }
                    var reader = new FileReader();
                    reader.onload = function(e){
                        document.execCommand("insertHTML", false, '<img src="' + e.target.result + '" style="max-width:100%;">');
                        editor.focus();
                    };
                    reader.readAsDataURL(file);
                    return true;
                }
                if(url){
                    document.execCommand("insertHTML", false, '<img src="' + escHtml(url) + '" style="max-width:100%;">');
                    editor.focus();
                    return true;
                }
                return { ok: false, msg: "请填写图片地址或选择本地图片文件" };
            }
        });
    }

    // ========== 挂载 ==========
    window.mountRichEditor = function(containerId, options){
        options = options || {};
        var container = document.getElementById(containerId);
        if(!container) return null;
        container.innerHTML = "";

        var colorRow = [
            '<div class="rt-tb-menu" style="padding:6px;">',
            '    <button type="button" data-fn="color" data-val="" class="rt-color-item"><span class="rt-color-dot" style="background:#333;"></span>默认色</button>',
            '    <button type="button" data-fn="color" data-val="#e02020" class="rt-color-item"><span class="rt-color-dot" style="background:#e02020;"></span>红色</button>',
            '    <button type="button" data-fn="color" data-val="#ff7d00" class="rt-color-item"><span class="rt-color-dot" style="background:#ff7d00;"></span>橙色</button>',
            '    <button type="button" data-fn="color" data-val="#00a650" class="rt-color-item"><span class="rt-color-dot" style="background:#00a650;"></span>绿色</button>',
            '    <button type="button" data-fn="color" data-val="#1f4e99" class="rt-color-item"><span class="rt-color-dot" style="background:#1f4e99;"></span>蓝色</button>',
            '    <button type="button" data-fn="color" data-val="#7b2fbe" class="rt-color-item"><span class="rt-color-dot" style="background:#7b2fbe;"></span>紫色</button>',
            '    <button type="button" data-fn="color" data-val="#333333" class="rt-color-item"><span class="rt-color-dot" style="background:#333333;"></span>黑色</button>',
            '</div>'
        ].join("");

        var sizeRow = [
            '<div class="rt-tb-menu">',
            '    <button type="button" data-fn="fontsize" data-val="1">12px</button>',
            '    <button type="button" data-fn="fontsize" data-val="2">14px</button>',
            '    <button type="button" data-fn="fontsize" data-val="3">16px</button>',
            '    <button type="button" data-fn="fontsize" data-val="4">18px</button>',
            '    <button type="button" data-fn="fontsize" data-val="5">24px</button>',
            '    <button type="button" data-fn="fontsize" data-val="6">32px</button>',
            '    <button type="button" data-fn="fontsize" data-val="7">48px</button>',
            '</div>'
        ].join("");

        var tb = document.createElement("div");
        tb.className = "rt-editor-toolbar";
        tb.innerHTML = [
            /* 标题 */
            '<div class="rt-tb-section" id="rtTitleSection">',
            '    <span class="tb-group-label">标题</span>',
            '    <div class="rt-tb-group" id="rtTitleDropdown">',
            '        <button type="button" class="tb-btn">标题 ▾</button>',
            '        <div class="rt-tb-dropdown"><div class="rt-tb-menu">',
            '            <button type="button" data-fn="heading" data-val="h1">标题 1</button>',
            '            <button type="button" data-fn="heading" data-val="h2">标题 2</button>',
            '            <button type="button" data-fn="heading" data-val="h3">标题 3</button>',
            '            <button type="button" data-fn="heading" data-val="h4">标题 4</button>',
            '            <button type="button" data-fn="heading" data-val="h5">标题 5</button>',
            '            <button type="button" data-fn="heading" data-val="p">正文</button>',
            '        </div></div>',
            '    </div>',
            '    <div class="rt-title-flat" id="rtTitleFlat" style="display:none;">',
            '        <button type="button" class="tb-btn" data-fn="heading" data-val="h1">标题1</button>',
            '        <button type="button" class="tb-btn" data-fn="heading" data-val="h2">标题2</button>',
            '        <button type="button" class="tb-btn" data-fn="heading" data-val="h3">标题3</button>',
            '        <button type="button" class="tb-btn" data-fn="heading" data-val="h4">标题4</button>',
            '        <button type="button" class="tb-btn" data-fn="heading" data-val="h5">标题5</button>',
            '        <button type="button" class="tb-btn" data-fn="heading" data-val="p">正文</button>',
            '    </div>',
            '</div>',
            '<span class="tb-sep"></span>',
            /* 文字（整体） */
            '<div class="rt-tb-section">',
            '    <span class="tb-group-label">文字</span>',
            '    <button type="button" class="tb-btn" data-cmd="bold" title="加粗（可取消）" style="font-weight:bold;">B</button>',
            '    <button type="button" class="tb-btn" data-cmd="italic" title="斜体（可取消）" style="font-style:italic;">I</button>',
            '    <button type="button" class="tb-btn" data-cmd="underline" title="下划线（可取消）" style="text-decoration:underline;">U</button>',
            '    <button type="button" class="tb-btn" data-cmd="strikeThrough" title="删除线（可取消）" style="text-decoration:line-through;">S</button>',
            '    <div class="rt-tb-group">',
            '        <button type="button" class="tb-btn">颜色 ▾</button>',
            '        <div class="rt-tb-dropdown">' + colorRow + '</div>',
            '    </div>',
            '    <div class="rt-tb-group">',
            '        <button type="button" class="tb-btn">字号 ▾</button>',
            '        <div class="rt-tb-dropdown">' + sizeRow + '</div>',
            '    </div>',
            '    <button type="button" class="tb-btn" data-cmd="removeFormat" title="清除选中文字的格式">清除格式</button>',
            '</div>',
            '<span class="tb-sep"></span>',
            /* 对齐（整体） */
            '<div class="rt-tb-section">',
            '    <span class="tb-group-label">对齐</span>',
            '    <button type="button" class="tb-btn" data-cmd="justifyLeft">左</button>',
            '    <button type="button" class="tb-btn" data-cmd="justifyCenter">中</button>',
            '    <button type="button" class="tb-btn" data-cmd="justifyRight">右</button>',
            '</div>',
            '<span class="tb-sep"></span>',
            /* 列表（整体） */
            '<div class="rt-tb-section">',
            '    <span class="tb-group-label">列表</span>',
            '    <div class="rt-tb-group">',
            '        <button type="button" class="tb-btn">列表 ▾</button>',
            '        <div class="rt-tb-dropdown"><div class="rt-tb-menu">',
            '            <button type="button" data-fn="list" data-val="ul">无序列表</button>',
            '            <button type="button" data-fn="list" data-val="ol">有序列表</button>',
            '        </div></div>',
            '    </div>',
            '</div>',
            '<span class="tb-sep"></span>',
            /* 缩进 */
            '<div class="rt-tb-section">',
            '    <span class="tb-group-label">缩进</span>',
            '    <div class="rt-tb-group">',
            '        <button type="button" class="tb-btn">缩进 ▾</button>',
            '        <div class="rt-tb-dropdown"><div class="rt-tb-menu">',
            '            <button type="button" data-fn="indent" data-val="in">增加缩进</button>',
            '            <button type="button" data-fn="indent" data-val="out">减少缩进</button>',
            '            <button type="button" data-fn="indent" data-val="first">首行缩进</button>',
            '        </div></div>',
            '    </div>',
            '</div>',
            '<span class="tb-sep"></span>',
            /* 插入 */
            '<div class="rt-tb-section">',
            '    <span class="tb-group-label">插入</span>',
            '    <div class="rt-tb-group">',
            '        <button type="button" class="tb-btn">插入 ▾</button>',
            '        <div class="rt-tb-dropdown"><div class="rt-tb-menu">',
            '            <button type="button" data-fn="insert" data-val="link">链接</button>',
            '            <button type="button" data-fn="insert" data-val="image">图片</button>',
            '        </div></div>',
            '    </div>',
            '</div>',
            '<span class="tb-sep"></span>',
            /* 表格 */
            '<div class="rt-tb-section">',
            '    <span class="tb-group-label">表格</span>',
            '    <div class="rt-tb-group">',
            '        <button type="button" class="tb-btn">表格操作 ▾</button>',
            '        <div class="rt-tb-dropdown"><div class="rt-tb-menu">',
            '            <button type="button" data-fn="table" data-val="insert">插入表格</button>',
            '            <button type="button" data-fn="table" data-val="addRow">加行</button>',
            '            <button type="button" data-fn="table" data-val="addCol">加列</button>',
            '            <button type="button" data-fn="table" data-val="delRow">删行</button>',
            '            <button type="button" data-fn="table" data-val="delCol">删列</button>',
            '            <button type="button" data-fn="table" data-val="delTable">删除表格</button>',
            '        </div></div>',
            '    </div>',
            '</div>',
            /* 撤销 / 重做：固定在最右侧 */
            '<span class="rt-right-group">',
            '    <button type="button" class="tb-btn" data-fn="history" data-val="undo" title="撤销（Ctrl+Z）">撤销</button>',
            '    <button type="button" class="tb-btn" data-fn="history" data-val="redo" title="重做（Ctrl+Y）">重做</button>',
            '    <button type="button" class="tb-btn" data-fn="settings" title="工具栏设置">设置</button>',
            '</span>'
        ].join("");

        // 编辑框
        var editor = document.createElement("div");
        editor.className = "rt-editor-box";
        editor.contentEditable = "true";
        if(options.height) editor.style.minHeight = options.height + "px";
        if(options.content) editor.innerHTML = options.content;

        container.appendChild(tb);
        container.appendChild(editor);

        // ===== 自定义撤销/重做历史栈（MutationObserver 自动记录所有变化） =====
        var history = [];
        var histIdx = -1;
        var restoring = false;

        function pushHist(){
            var cur = editor.innerHTML;
            if(history[histIdx] === cur) return; // 内容无变化不记录
            history = history.slice(0, histIdx + 1);
            history.push(cur);
            if(history.length > 120) history.shift();
            histIdx = history.length - 1;
        }
        // 恢复内容到指定快照（光标移到末尾，便于继续操作）
        function restoreTo(html){
            restoring = true;
            editor.innerHTML = html;
            refreshStates();
            try{
                editor.focus();
                var range = document.createRange();
                range.selectNodeContents(editor);
                range.collapse(false);
                var sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            }catch(e){}
            // 延迟复位 restoring，确保本轮 MutationObserver 微任务执行时仍为 true
            setTimeout(function(){ restoring = false; }, 0);
        }
        function doUndo(){
            if(histIdx > 0){
                histIdx--;
                restoreTo(history[histIdx]);
            }
        }
        function doRedo(){
            if(histIdx < history.length - 1){
                histIdx++;
                restoreTo(history[histIdx]);
            }
        }

        // MutationObserver：监听编辑框所有变化（文字/节点/属性含 text-indent），自动入历史
        var moTimer = null;
        var mo = new MutationObserver(function(){
            if(restoring) return;
            clearTimeout(moTimer);
            moTimer = setTimeout(function(){
                if(!restoring) pushHist();
            }, 300);
        });
        mo.observe(editor, {
            childList: true,
            subtree: true,
            characterData: true,
            attributes: true
        });

        // 拦截 Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z
        editor.addEventListener("keydown", function(e){
            if((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z"){
                e.preventDefault();
                if(e.shiftKey) doRedo(); else doUndo();
            }else if((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y"){
                e.preventDefault();
                doRedo();
            }
        });

        // 刷新按钮高亮状态
        function refreshStates(){
            // B/I/U/S / alignment
            tb.querySelectorAll("[data-cmd]").forEach(function(btn){
                var cmd = btn.getAttribute("data-cmd");
                var on = false;
                try{
                    if(cmd.indexOf("justify") === 0){
                        try{ on = document.queryCommandState(cmd); }catch(e2){ on = false; }
                    }else if(cmd === "removeFormat"){
                        on = false;
                    }else{
                        on = document.queryCommandState(cmd);
                    }
                }catch(e){ on = false; }
                btn.classList.toggle("active", on);
            });
            // heading: match current block tag
            var fb = "";
            try{ fb = (document.queryCommandValue("formatBlock") || "").toLowerCase().replace(/[<>]/g, ""); }catch(e){}
            tb.querySelectorAll("[data-fn=heading]").forEach(function(btn){
                btn.classList.toggle("active", btn.getAttribute("data-val") === fb);
            });
            // font color
            var fc = "";
            try{ fc = (document.queryCommandValue("foreColor") || "").toLowerCase(); }catch(e){}
            var colorMatched = false;
            tb.querySelectorAll("[data-fn=color]").forEach(function(btn){
                var val = btn.getAttribute("data-val") || "";
                var on = false;
                if(val){ on = (hexToRgbStr(val) === fc); if(on) colorMatched = true; }
                btn.classList.toggle("active", on);
            });
            tb.querySelectorAll("[data-fn=color][data-val=\"\"]").forEach(function(btn){
                btn.classList.toggle("active", !colorMatched);
            });
            // font size
            var fs = "";
            try{ fs = (document.queryCommandValue("fontSize") || ""); }catch(e){}
            tb.querySelectorAll("[data-fn=fontsize]").forEach(function(btn){
                btn.classList.toggle("active", btn.getAttribute("data-val") === fs);
            });
            // list
            var ulOn = false, olOn = false;
            try{ ulOn = document.queryCommandState("insertUnorderedList"); }catch(e){}
            try{ olOn = document.queryCommandState("insertOrderedList"); }catch(e){}
            tb.querySelectorAll("[data-fn=list]").forEach(function(btn){
                var v = btn.getAttribute("data-val");
                btn.classList.toggle("active", (v === "ul" && ulOn) || (v === "ol" && olOn));
            });
            // first-line indent
            var tiOn = false;
            var sel = window.getSelection();
            if(sel && sel.rangeCount){
                var node = sel.anchorNode;
                if(node && node.nodeType === 3) node = node.parentNode;
                var blk = node ? node.closest("p,div,h1,h2,h3,h4,h5,pre,blockquote,li") : null;
                if(blk && blk !== editor && editor.contains(blk)){
                    tiOn = (blk.style.textIndent === "2em");
                }
            }
            tb.querySelectorAll("[data-fn=indent]").forEach(function(btn){
                if(btn.getAttribute("data-val") === "first") btn.classList.toggle("active", tiOn);
                else btn.classList.toggle("active", false);
            });
        }
        editor.addEventListener("keyup", refreshStates);
        editor.addEventListener("mouseup", refreshStates);
        document.addEventListener("selectionchange", refreshStates);

        // 点击编辑框内的链接 → 打开修改弹窗
        editor.addEventListener("click", function(e){
            var a = e.target && e.target.closest ? e.target.closest("a") : null;
            if(a && editor.contains(a)){
                e.preventDefault();
                insertLinkFlow(editor, a);
                return;
            }
            refreshStates();
        });

        // 绑定：execCommand 命令按钮
        tb.querySelectorAll("[data-cmd]").forEach(function(btn){
            btn.addEventListener("click", function(){
                exec(btn.getAttribute("data-cmd"));
                editor.focus();
                refreshStates();
                pushHist();
            });
        });
        // 绑定：功能按钮
        tb.querySelectorAll("[data-fn]").forEach(function(btn){
            btn.addEventListener("click", function(){
                var fn = btn.getAttribute("data-fn");
                var val = btn.getAttribute("data-val");
                if(fn === "settings"){ openSettings(); return; }
                if(fn === "history"){
                    if(val === "undo") doUndo();
                    else if(val === "redo") doRedo();
                    return;
                }
                if(fn === "heading") setHeading(editor, val);
                else if(fn === "color") setColor(editor, val);
                else if(fn === "fontsize") setFontSize(editor, val);
                else if(fn === "indent") setIndent(editor, val);
                else if(fn === "list") toggleList(editor, val);
                else if(fn === "insert"){
                    if(val === "link") insertLinkFlow(editor, null);
                    else if(val === "image") insertImageFlow(editor);
                }
                else if(fn === "table"){
                    if(val === "insert") insertTable(editor);
                    else if(val === "addRow") addRow(editor);
                    else if(val === "addCol") addCol(editor);
                    else if(val === "delRow") delRow(editor);
                    else if(val === "delCol") delCol(editor);
                    else if(val === "delTable") delTable(editor);
                }
                editor.focus();
                refreshStates();
                pushHist();
            });
        });

        // 标题显示模式（localStorage 持久化）
        function applyTitleMode(on){
            var sec = tb.querySelector("#rtTitleSection");
            var drop = tb.querySelector("#rtTitleDropdown");
            var flat = tb.querySelector("#rtTitleFlat");
            if(!sec || !drop || !flat) return;
            if(on){
                drop.style.display = "none";
                flat.style.display = "inline-flex";
                sec.classList.add("rt-title-expanded");
            }else{
                drop.style.display = "";
                flat.style.display = "none";
                sec.classList.remove("rt-title-expanded");
            }
        }
        function openSettings(){
            var expanded = false;
            try{ expanded = localStorage.getItem("rtTitleExpanded") === "1"; }catch(e){}
            showRtModal({
                title: "工具栏设置",
                fields: [
                    { id: "rtCfgTitle", label: "标题按钮直接展开显示（独占一行）", type: "checkbox", checked: expanded, tip: "开启后标题各按钮平铺在一行；关闭时标题为悬浮下拉菜单" }
                ],
                okText: "保存",
                onOk: function(vals){
                    var on = !!vals.rtCfgTitle;
                    try{ localStorage.setItem("rtTitleExpanded", on ? "1" : "0"); }catch(e){}
                    applyTitleMode(on);
                    return true;
                }
            });
        }
        try{ applyTitleMode(localStorage.getItem("rtTitleExpanded") === "1"); }catch(e){}

        // 初始快照
        pushHist();

        return {
            getContent: function(){ return editor.innerHTML; },
            getText: function(){ return (editor.innerText || "").trim(); },
            setContent: function(html){
                editor.innerHTML = html || "";
                history = [editor.innerHTML];
                histIdx = 0;
            }
        };
    };
})();
