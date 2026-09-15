(function () {
  'use strict';

  var currentSlide = 0;
  var totalSlides = 0;

  fetch('presentation.json')
    .then(function (r) { return r.json(); })
    .then(function (manifest) {
      var slidesEl = document.getElementById('slides');
      var sections = manifest.sections;
      totalSlides = sections.length;

      var fetches = sections.map(function (sec) {
        return fetch(sec.file).then(function (r) { return r.text(); });
      });

      return Promise.all(fetches).then(function (htmls) {
        htmls.forEach(function (html, i) {
          var div = document.createElement('div');
          div.className = 'slide';
          div.id = sections[i].id;

          var content = document.createElement('div');
          content.className = 'slide-content';
          content.innerHTML = html;

          var chrome = content.querySelectorAll('.rh-bar-t, .rh-bar-b, .rh-privacy, .rh-section-footer, .hero-headline, .title-presenter, .title-white-strip');
          chrome.forEach(function (el) {
            content.removeChild(el);
            div.appendChild(el);
          });

          div.appendChild(content);
          slidesEl.appendChild(div);
        });

        buildAgendaGrid(manifest);

        var logoScript = document.createElement('script');
        logoScript.src = 'js/rh-logo.js';
        logoScript.onload = function () {
          if (window.RH_LOGO_SRC) {
            document.querySelectorAll('.rh-logo-img').forEach(function (img) {
              img.src = window.RH_LOGO_SRC;
            });
          }
          var navScript = document.createElement('script');
          navScript.src = 'js/interactions.js';
          document.body.appendChild(navScript);
        };
        document.body.appendChild(logoScript);

        updateCounter();
      });
    })
    .catch(function (err) {
      document.getElementById('slides').innerHTML =
        '<div class="slide" style="display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;">' +
        '<h2 style="color:#EE0000;">Failed to load presentation</h2>' +
        '<p style="color:#666;">' + err.message + '</p>' +
        '<p style="color:#999;font-size:13px;">Serve via HTTP: <code>python3 -m http.server</code></p></div>';
    });

  function buildAgendaGrid(manifest) {
    var grid = document.getElementById('agenda-grid');
    if (!grid || !manifest.agenda) return;
    manifest.agenda.forEach(function (item) {
      var card = document.createElement('div');
      card.className = 'agenda-card';
      card.style.borderTopColor = item.accent;
      card.innerHTML =
        '<div class="agenda-num">' + item.num + '</div>' +
        '<div class="agenda-title">' + item.title + '</div>' +
        '<div class="agenda-desc">' + item.desc + '</div>';
      card.addEventListener('click', function () {
        var target = document.getElementById(item.target);
        if (target) {
          var slides = document.querySelectorAll('.slide');
          for (var j = 0; j < slides.length; j++) {
            if (slides[j] === target) { goToSlide(j); break; }
          }
        }
      });
      grid.appendChild(card);
    });
  }

  function goToSlide(n) {
    n = Math.max(0, Math.min(totalSlides - 1, n));
    currentSlide = n;
    document.getElementById('slides').style.transform = 'translateX(-' + (n * 1280) + 'px)';
    updateCounter();
    try {
      var ch = new BroadcastChannel('presenter-sync');
      ch.postMessage({ type: 'navigate', index: n });
      ch.close();
    } catch (e) {}
  }

  function updateCounter() {
    var el = document.getElementById('slide-counter');
    if (el) el.textContent = (currentSlide + 1) + ' / ' + totalSlides;
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); goToSlide(currentSlide + 1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); goToSlide(currentSlide - 1); }
    if (e.key === 'Home') { e.preventDefault(); goToSlide(0); }
    if (e.key === 'End') { e.preventDefault(); goToSlide(totalSlides - 1); }
  });

  document.getElementById('viewport').addEventListener('click', function (e) {
    var rect = this.getBoundingClientRect();
    var x = e.clientX - rect.left;
    if (x < rect.width / 2) goToSlide(currentSlide - 1);
    else goToSlide(currentSlide + 1);
  });

  var prevBtn = document.getElementById('btn-prev');
  var nextBtn = document.getElementById('btn-next');
  if (prevBtn) prevBtn.addEventListener('click', function (e) { e.stopPropagation(); goToSlide(currentSlide - 1); });
  if (nextBtn) nextBtn.addEventListener('click', function (e) { e.stopPropagation(); goToSlide(currentSlide + 1); });

  window.goToSlide = goToSlide;
  window.getCurrentSlide = function () { return currentSlide; };
  window.getTotalSlides = function () { return totalSlides; };
})();
