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
 * ============================================================ */
(function(){
    // 注入编辑器样式（只注入一次）
    if(!document.getElementById("rtEditorStyle")){
        var st = document.createElement("style");
        st.id = "rtEditorStyle";
        st.textContent = [
            ".rt-editor-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:10px;background:#f7f7f7;border:1px solid #eee;border-radius:4px;margin-bottom:8px;}",
            ".rt-editor-toolbar .tb-group-label{font-size:12px;color:#888;white-space:nowrap;}",
            ".rt-editor-toolbar .tb-btn{background:#fff;border:1px solid #ddd;border-radius:4px;padding:4px 12px;cursor:pointer;font-size:13px;line-height:1.5;color:#333;}",
            ".rt-editor-toolbar .tb-btn:hover{background:#f0f4ff;color:#1f4e99;border-color:#1f4e99;}",
            ".rt-editor-toolbar .tb-sep{width:1px;height:18px;background:#ddd;align-self:center;}",
            ".rt-tb-group{position:relative;display:inline-block;}",
            ".rt-tb-group:hover .rt-tb-dropdown{display:block;}",
            ".rt-tb-dropdown{display:none;position:absolute;left:0;top:100%;z-index:999;min-width:120px;padding-top:4px;background:transparent;}",
            ".rt-tb-dropdown::before{content:'';position:absolute;top:0;left:0;right:0;height:4px;}",
            ".rt-tb-dropdown .rt-tb-menu{background:#fff;border:1px solid #ddd;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.15);padding:4px 0;}",
            ".rt-tb-dropdown button{display:block;width:100%;border:none;background:none;text-align:left;padding:8px 12px;cursor:pointer;font-size:13px;color:#333;white-space:nowrap;}",
            ".rt-tb-dropdown button:hover{background:#f0f4ff;color:#1f4e99;}",
            ".rt-editor-box{min-height:160px;border:1px solid #ccc;border-radius:4px;padding:8px;background:#fff;line-height:1.8;outline:none;}",
            ".rt-editor-box:focus{border-color:#1f4e99;}"
        ].join("\n");
        document.head.appendChild(st);
    }

    function exec(cmd){
        document.execCommand(cmd, false, null);
    }

    // 光标所在表格
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
    // 光标所在行
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
    // 光标所在单元格
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
    // 插入默认 2x2 表格
    function insertTable(editor){
        var html = '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;margin:8px 0;"><tr><td>&nbsp;</td><td>&nbsp;</td></tr><tr><td>&nbsp;</td><td>&nbsp;</td></tr></table>';
        document.execCommand("insertHTML", false, html);
        editor.focus();
    }
    // 底部加一行
    function addRow(editor){
        var tb = getTable(editor);
        if(!tb){ alert("请先点击表格内的任意位置"); return; }
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
    // 右侧加一列
    function addCol(editor){
        var tb = getTable(editor);
        if(!tb){ alert("请先点击表格内的任意位置"); return; }
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
    // 删除光标所在行
    function delRow(editor){
        var tb = getTable(editor);
        if(!tb){ alert("请先点击表格内的任意位置"); return; }
        var tr = getRow(editor);
        if(!tr){ alert("请先点击要删除的那一行"); return; }
        if(tb.rows.length <= 1){ alert("表格至少保留一行"); return; }
        tb.deleteRow(tr.rowIndex);
        editor.focus();
    }
    // 删除光标所在列
    function delCol(editor){
        var tb = getTable(editor);
        if(!tb){ alert("请先点击表格内的任意位置"); return; }
        var td = getCell(editor);
        if(!td){ alert("请先点击要删除的那一列中的任意单元格"); return; }
        if(tb.rows[0].cells.length <= 1){ alert("表格至少保留一列"); return; }
        var idx = td.cellIndex;
        for(var i=0;i<tb.rows.length;i++){
            if(tb.rows[i].cells[idx]) tb.rows[i].deleteCell(idx);
        }
        editor.focus();
    }
    // 删除整个表格
    function delTable(editor){
        var tb = getTable(editor);
        if(!tb){ alert("请先点击表格内的任意位置"); return; }
        if(confirm("确定删除该表格吗？")){
            tb.remove();
            editor.focus();
        }
    }

    // 挂载富文本编辑器
    window.mountRichEditor = function(containerId, options){
        options = options || {};
        var container = document.getElementById(containerId);
        if(!container) return null;
        container.innerHTML = "";

        // 工具栏
        var tb = document.createElement("div");
        tb.className = "rt-editor-toolbar";
        tb.innerHTML = [
            '<span class="tb-group-label">文字</span>',
            '<button type="button" class="tb-btn" data-cmd="bold" title="加粗" style="font-weight:bold;">B</button>',
            '<button type="button" class="tb-btn" data-cmd="italic" title="斜体" style="font-style:italic;">I</button>',
            '<button type="button" class="tb-btn" data-cmd="underline" title="下划线" style="text-decoration:underline;">U</button>',
            '<button type="button" class="tb-btn" data-cmd="strikeThrough" title="删除线" style="text-decoration:line-through;">S</button>',
            '<button type="button" class="tb-btn" data-cmd="removeFormat" title="清除格式">清除格式</button>',
            '<span class="tb-sep"></span>',
            '<span class="tb-group-label">对齐</span>',
            '<button type="button" class="tb-btn" data-cmd="justifyLeft">左对齐</button>',
            '<button type="button" class="tb-btn" data-cmd="justifyCenter">居中</button>',
            '<button type="button" class="tb-btn" data-cmd="justifyRight">右对齐</button>',
            '<span class="tb-sep"></span>',
            '<span class="tb-group-label">列表</span>',
            '<button type="button" class="tb-btn" data-cmd="insertUnorderedList" title="无序列表">• 列表</button>',
            '<button type="button" class="tb-btn" data-cmd="insertOrderedList" title="有序列表">1. 列表</button>',
            '<button type="button" class="tb-btn" data-cmd="insertHorizontalRule" title="插入水平线">横线</button>',
            '<span class="tb-sep"></span>',
            '<span class="tb-group-label">表格</span>',
            '<div class="rt-tb-group">',
            '    <button type="button" class="tb-btn">表格操作 ▾</button>',
            '    <div class="rt-tb-dropdown">',
            '        <div class="rt-tb-menu">',
            '            <button type="button" data-tb="insert">插入表格</button>',
            '            <button type="button" data-tb="addRow">加行</button>',
            '            <button type="button" data-tb="addCol">加列</button>',
            '            <button type="button" data-tb="delRow">删行</button>',
            '            <button type="button" data-tb="delCol">删列</button>',
            '            <button type="button" data-tb="delTable">删除表格</button>',
            '        </div>',
            '    </div>',
            '</div>'
        ].join("");

        // 编辑框
        var editor = document.createElement("div");
        editor.className = "rt-editor-box";
        editor.contentEditable = "true";
        if(options.height) editor.style.minHeight = options.height + "px";
        if(options.content) editor.innerHTML = options.content;

        container.appendChild(tb);
        container.appendChild(editor);

        // 绑定工具栏事件
        tb.querySelectorAll("[data-cmd]").forEach(function(btn){
            btn.addEventListener("click", function(){
                exec(btn.getAttribute("data-cmd"));
                editor.focus();
            });
        });
        tb.querySelectorAll("[data-tb]").forEach(function(btn){
            btn.addEventListener("click", function(){
                var op = btn.getAttribute("data-tb");
                if(op === "insert") insertTable(editor);
                else if(op === "addRow") addRow(editor);
                else if(op === "addCol") addCol(editor);
                else if(op === "delRow") delRow(editor);
                else if(op === "delCol") delCol(editor);
                else if(op === "delTable") delTable(editor);
                editor.focus();
            });
        });

        return {
            getContent: function(){ return editor.innerHTML; },
            getText: function(){ return (editor.innerText || "").trim(); },
            setContent: function(html){ editor.innerHTML = html || ""; }
        };
    };
})();
