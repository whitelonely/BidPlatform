/* ============================================================
 * 文件预览公共模块
 * previewFile(url, filename)：
 *   - 图片（jpg/jpeg/png/gif/bmp/webp）：弹窗显示大图
 *   - 其他（PDF/TXT 等）：浏览器新窗口打开（PDF 需调用方传 inline 预览地址）
 * ============================================================ */
(function(){
    var IMG_EXTS = ["jpg","jpeg","png","gif","bmp","webp"];

    function extOf(filename){
        return (filename || "").split(".").pop().toLowerCase();
    }

    // 图片弹窗预览
    function openImagePreview(url){
        var mask = document.getElementById("imgPreviewMask");
        if(!mask){
            mask = document.createElement("div");
            mask.id = "imgPreviewMask";
            mask.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.6);z-index:9999;display:none;align-items:center;justify-content:center;cursor:zoom-out;";
            mask.addEventListener("click", function(){ mask.style.display = "none"; });
            document.body.appendChild(mask);
        }
        mask.innerHTML = '<img src="' + url + '" style="max-width:92%;max-height:92%;box-shadow:0 4px 30px rgba(0,0,0,.4);background:#fff;">';
        mask.style.display = "flex";
    }

    window.previewFile = function(url, filename){
        var ext = extOf(filename);
        if(IMG_EXTS.indexOf(ext) >= 0){
            openImagePreview(url);
        }else{
            window.open(url, "_blank");
        }
    };
})();
