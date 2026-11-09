// Collapse the docs menu on small screens (it is open, and fully usable, without this script).
(function () {
  var nav = document.querySelector("details.docnav");
  if (nav && window.matchMedia("(max-width: 62rem)").matches) nav.removeAttribute("open");
})();

// Adds a "Copy" button to every code block. The page works without it.
(function () {
  var blocks = document.querySelectorAll("pre");
  for (var i = 0; i < blocks.length; i++) {
    (function (pre) {
      if (!navigator.clipboard) return;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "copy";
      b.textContent = "Copy";
      b.addEventListener("click", function () {
        navigator.clipboard.writeText(pre.innerText.replace(/\nCopy$/, "")).then(function () {
          b.textContent = "Copied";
          setTimeout(function () { b.textContent = "Copy"; }, 1800);
        });
      });
      pre.appendChild(b);
    })(blocks[i]);
  }
})();
