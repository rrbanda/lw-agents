(async function () {
  'use strict';

  var config;
  try {
    var resp = await fetch('presentation.json');
    config = await resp.json();
  } catch (e) {
    document.querySelector('main').innerHTML =
      '<p style="color:#ef4444;padding:40px;text-align:center;">Failed to load presentation.json. ' +
      'Make sure you are serving the site over HTTP (e.g. <code>python3 -m http.server</code>).</p>';
    return;
  }

  var nav = document.getElementById('side-nav');
  var main = document.querySelector('main');
  var footer = document.querySelector('footer');
  var sections = config.sections;

  nav.innerHTML = sections.map(function (s, i) {
    var cls = i === 0 ? ' class="active"' : '';
    var label = s.navLabel.replace(/&/g, '&amp;');
    return '<a href="#' + s.id + '" data-label="' + label + '"' + cls + '></a>';
  }).join('\n  ');

  var fetches = sections.map(function (s) {
    return fetch(s.file).then(function (r) {
      if (!r.ok) throw new Error(s.file + ': ' + r.status);
      return r.text();
    });
  });

  var htmls;
  try {
    htmls = await Promise.all(fetches);
  } catch (e) {
    main.innerHTML = '<p style="color:#ef4444;padding:40px;">Failed to load section: ' + e.message + '</p>';
    return;
  }

  var mainHTML = '';
  sections.forEach(function (s, i) {
    var isHero = s.id === 'hero';
    var cls = isHero ? 'section visible' : 'section';
    mainHTML += '<section id="' + s.id + '" class="' + cls + '">\n';
    mainHTML += htmls[i];

    if (i < sections.length - 1) {
      var next = sections[i + 1];
      if (isHero) {
        mainHTML += '\n  <a href="#' + next.id + '" class="scroll-indicator" title="Scroll down">&#8595;</a>';
      } else {
        mainHTML += '\n  <a href="#' + next.id + '" class="section-arrow" title="Next: ' +
          next.navLabel.replace(/&/g, '&amp;') + '">&#8595;</a>';
      }
    }
    mainHTML += '\n</section>\n\n';
  });

  main.innerHTML = mainHTML;

  var agendaGrid = document.getElementById('agenda-grid');
  if (agendaGrid && config.agenda) {
    agendaGrid.innerHTML = config.agenda.map(function (a) {
      return '<a href="#' + a.target + '" class="agenda-card" style="--card-accent:' + a.accent + ';">' +
        '<span class="agenda-num">' + a.num + '</span>' +
        '<span class="agenda-title">' + a.title + '</span>' +
        '<span class="agenda-desc">' + a.desc + '</span>' +
        '</a>';
    }).join('\n      ');
  }

  // Populate section footer logos from the extracted base64 constant
  var logoSrc = window.RH_LOGO_SRC || '';
  if (logoSrc) {
    var logoImgs = document.querySelectorAll('.rh-logo-img');
    for (var li = 0; li < logoImgs.length; li++) {
      logoImgs[li].src = logoSrc;
    }
  }

  if (footer && config.footer) {
    var logoTag = logoSrc
      ? '<img src="' + logoSrc + '" alt="Red Hat" style="height:24px;">'
      : '<span style="color:var(--rh-red);font:700 14px var(--font);">Red Hat</span>';
    footer.innerHTML =
      '<div class="footer-inner">' +
        '<div class="footer-logo">' + logoTag + '</div>' +
        '<p class="footer-title">' + config.footer.title + '</p>' +
        '<p class="footer-text">' + config.footer.text + '</p>' +
        '<p class="footer-privacy">Confidential: Red Hat associate and NDA partner use only. No further distribution.</p>' +
      '</div>';
  }

  if (config.presenterGroups) {
    var configScript = document.createElement('script');
    configScript.id = 'presenter-config';
    configScript.type = 'application/json';
    configScript.textContent = JSON.stringify(config.presenterGroups);
    document.body.appendChild(configScript);
  }

  document.body.classList.remove('loading');

  // Load rh-logo.js first (provides window.RH_LOGO_SRC), then interactions
  var logoScript = document.createElement('script');
  logoScript.src = 'js/rh-logo.js';
  logoScript.onload = function () {
    // Now that logo is available, populate images
    var src = window.RH_LOGO_SRC || '';
    if (src) {
      var imgs = document.querySelectorAll('.rh-logo-img');
      for (var k = 0; k < imgs.length; k++) imgs[k].src = src;
      // Also update footer logo if it was a fallback
      var fLogo = document.querySelector('.footer-logo img');
      if (fLogo && !fLogo.src) fLogo.src = src;
    }
    var script = document.createElement('script');
    script.src = 'js/interactions.js';
    script.defer = true;
    document.body.appendChild(script);
  };
  logoScript.onerror = function () {
    var script = document.createElement('script');
    script.src = 'js/interactions.js';
    script.defer = true;
    document.body.appendChild(script);
  };
  document.body.appendChild(logoScript);
})();
