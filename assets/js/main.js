/* negolosom.ru — вся интерактивность сайта.
 *
 * Порядок здесь не случайный: сначала поднимается всё, что написано на голом
 * DOM и работает всегда (меню, подсказки, шапка), и только потом —
 * прогрессивные улучшения на вендорных библиотеках. Если библиотека не
 * доехала, соответствующий блок молча не инициализируется, а страница
 * остаётся полностью рабочей.
 *
 * Библиотеки: GSAP + ScrollTrigger, Lenis, Embla Carousel (+ auto-scroll,
 * wheel-gestures). Версии и хеши — в assets/js/vendor/VENDOR.md.
 */
(function () {
  'use strict';

  /* Библиотеки подгружаются после первой отрисовки (см. loadVendors в конце
     файла), поэтому флаги пересчитываются, а не берутся один раз на старте. */
  var has = { gsap: false, lenis: false, embla: false };

  function refreshFeatures() {
    has.gsap = !!(window.gsap && window.ScrollTrigger);
    has.lenis = typeof window.Lenis === 'function';
    has.embla = typeof window.EmblaCarousel === 'function';
  }

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  var lenis = null;

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  };

  var headerOffset = function () {
    var header = $('[data-header]');
    return (header ? header.offsetHeight : 64) + 12;
  };

  /* Прокрутка страницы блокируется в двух местах сразу: у Lenis — своим
     методом, у браузера — классом на body. Одного из них мало: Lenis не знает
     про нативный скролл тач-устройства, а класс не останавливает Lenis. */
  function lockScroll(locked) {
    document.body.classList.toggle('is-locked', locked);
    if (!lenis) return;
    if (locked) lenis.stop(); else lenis.start();
  }


  /* --- Ссылка «к основному содержимому» ---------------------------------- */

  /* Lenis перехватывает клики по якорям и не переносит фокус. Для скип-линка
     это убивает весь смысл: страница прокручивается, а таб продолжается от
     старого места. Поэтому обрабатываем его руками. */
  function initSkipLink() {
    var link = $('.skip-link');
    var main = $('#main');
    if (!link || !main) return;

    link.addEventListener('click', function (e) {
      e.preventDefault();
      if (lenis) lenis.scrollTo(main, { immediate: true });
      else main.scrollIntoView();
      main.focus({ preventScroll: true });
    });
  }


  /* --- Что видно сразу, то не прячем -------------------------------------- */

  /* Класс .js-anim из <head> ставит стартовую прозрачность всем элементам с
     data-reveal. Для тех, что уже в первом экране, это означает: текст не
     нарисован, пока не доедет GSAP, — а он грузится после события load. На
     странице вопросов именно такой абзац оказывался самым крупным элементом
     отрисовки, и Lighthouse считал её 3,9 с.

     Поэтому сразу после разбора документа снимаем разметку появления со
     всего, что попадает в первый экран: такой элемент виден с первого кадра
     и в анимации потом не участвует. */
  function unhideAboveFold() {
    if (!document.documentElement.classList.contains('js-anim')) return;
    var limit = window.innerHeight * 0.9;
    $$('[data-reveal], [data-reveal-group]').forEach(function (el) {
      if (el.getBoundingClientRect().top < limit) {
        el.removeAttribute('data-reveal');
        el.removeAttribute('data-reveal-group');
      }
    });
  }


  /* --- Состояние шапки ---------------------------------------------------- */

  function initHeaderState() {
    var header = $('[data-header]');
    if (!header) return;

    var ticking = false;
    var apply = function () {
      header.classList.toggle('is-stuck', window.scrollY > 40);
      ticking = false;
    };

    apply();
    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(apply);
    }, { passive: true });
  }


  /* --- Мобильное меню ----------------------------------------------------- */

  /* Фон убирается из таба и из дерева доступности атрибутом inert — это
     надёжнее рукописной ловушки фокуса и заодно прячет фон от скринридера. */
  function initBurger() {
    var menu = $('[data-menu]');
    var openBtn = $('[data-menu-open]');
    var closeBtn = $('[data-menu-close]');
    if (!menu || !openBtn) return;

    var background = [$('main'), $('.site-footer'), $('[data-fab]'), $('[data-header]')];

    var setInert = function (state) {
      background.forEach(function (el) {
        if (!el) return;
        if (state) el.setAttribute('inert', '');
        else el.removeAttribute('inert');
      });
    };

    var open = function () {
      menu.hidden = false;
      openBtn.setAttribute('aria-expanded', 'true');
      setInert(true);
      lockScroll(true);
      if (closeBtn) closeBtn.focus();
    };

    var close = function () {
      menu.hidden = true;
      openBtn.setAttribute('aria-expanded', 'false');
      setInert(false);
      lockScroll(false);
      openBtn.focus();
    };

    openBtn.addEventListener('click', open);
    if (closeBtn) closeBtn.addEventListener('click', close);

    // Переход по пункту меню закрывает его — иначе оверлей останется висеть
    // поверх той секции, к которой только что уехали.
    $$('a', menu).forEach(function (a) {
      a.addEventListener('click', function () {
        if (!menu.hidden) close();
      });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !menu.hidden) close();
    });

    // Экран расширился до десктопа, пока меню было открыто.
    window.matchMedia('(min-width: 840px)').addEventListener('change', function (e) {
      if (e.matches && !menu.hidden) close();
    });
  }


  /* --- Меню «Скачать» в шапке ---------------------------------------------- */

  /* Само раскрытие делает <details> — оно работает и без скриптов. Здесь
     только то, чего у <details> нет из коробки: закрытие по Escape и по
     клику мимо. В шапке блок виден с 840 px; на телефоне обе ссылки лежат
     в бургер-меню обычными кнопками. */
  function initDownloadMenu() {
    var dl = $('[data-dl]');
    if (!dl) return;

    var close = function (returnFocus) {
      if (!dl.open) return;
      dl.open = false;
      if (returnFocus) $('summary', dl).focus();
    };

    document.addEventListener('click', function (e) {
      if (!dl.contains(e.target)) close(false);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') close(true);
    });

    dl.addEventListener('focusout', function (e) {
      if (!dl.contains(e.relatedTarget)) close(false);
    });
  }


  /* --- Подсказки «i» ------------------------------------------------------ */

  /* Это disclosure, а не tooltip: открывается по клику и по клавиатуре,
     закрывается по Escape и клику вне. Паттерн tooltip на hover не работает
     на тач-экранах и не закрывается с клавиатуры.
     Наведение мышью открывает подсказку силами CSS — так она работает и при
     выключенном JS. */
  function initDisclosures() {
    var triggers = $$('[data-disclosure]');
    if (!triggers.length) return;

    var closeAll = function (except) {
      triggers.forEach(function (btn) {
        if (btn === except) return;
        btn.setAttribute('aria-expanded', 'false');
        var panel = document.getElementById(btn.getAttribute('aria-controls'));
        if (panel) panel.hidden = true;
      });
    };

    triggers.forEach(function (btn) {
      var panel = document.getElementById(btn.getAttribute('aria-controls'));
      if (!panel) return;

      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var willOpen = btn.getAttribute('aria-expanded') !== 'true';
        closeAll(btn);
        btn.setAttribute('aria-expanded', String(willOpen));
        panel.hidden = !willOpen;
      });
    });

    document.addEventListener('click', function () { closeAll(null); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeAll(null);
    });
  }


  /* --- Плавающая кнопка --------------------------------------------------- */

  /* --- Карусель экранов ----------------------------------------------------

     Про колесо мыши. Вьюпорту карусели нельзя ставить data-lenis-prevent:
     Lenis тогда не обрабатывает прокрутку в этой зоне, а сам блок при живом
     Embla имеет overflow:hidden — и страница намертво встаёт, стоит навести
     курсор на карусель.

     Разделение выходит само собой: Lenis работает только по вертикали и
     смотрит на deltaY, а плагин wheel-gestures гасит событие лишь тогда,
     когда жест преимущественно горизонтальный (preventWheelAction берётся из
     оси карусели, то есть 'x'). Вертикальное колесо листает страницу,
     горизонтальный жест трекпада — карусель. */

  var ICONS = {
    prev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>',
    next: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>',
    pause: '<svg class="icon-pause" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>',
    play: '<svg class="icon-play" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15l12-7.5z"/></svg>'
  };

  function makeButton(label, html) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'carousel__btn';
    btn.innerHTML = '<span class="visually-hidden">' + label + '</span>' + html;
    return btn;
  }

  function initCarousel() {
    var root = $('[data-carousel]');
    if (!root) return;

    var viewport = $('[data-carousel-viewport]', root);
    var track = $('[data-carousel-track]', root);
    var controls = $('[data-carousel-controls]');
    if (!viewport || !track) return;

    // Без Embla карусель остаётся обычным горизонтальным скроллом со
    // scroll-snap — она полностью работоспособна, просто без автопрокрутки.
    if (!has.embla) return;

    /* Embla отключает зацикливание, если суммарная ширина слайдов меньше
       ширины вьюпорта. Девять карточек дают около 2900 px — на мониторе 3440
       этого не хватит, и лента упрётся в край. Тогда дублируем комплект:
       сетевой стоимости ноль, картинки те же и берутся из кеша.

       На телефоне дублировать нечего: девять карточек и так в семь раз шире
       экрана, а лишние девять узлов с картинками — это заметная работа
       раскладки на слабом процессоре. */
    if (track.scrollWidth < viewport.clientWidth * 1.8) {
      $$('.carousel__slide', track).forEach(function (slide) {
        var copy = slide.cloneNode(true);
        copy.setAttribute('aria-hidden', 'true');
        $$('a, button', copy).forEach(function (el) { el.setAttribute('tabindex', '-1'); });
        $$('img', copy).forEach(function (img) { img.setAttribute('loading', 'lazy'); });
        track.appendChild(copy);
      });
    }

    viewport.classList.add('is-embla');

    var plugins = [];
    if (window.EmblaCarouselWheelGestures) {
      // Без forceWheelAxis: вертикальное колесо продолжает крутить страницу.
      // Иначе на бесконечной карусели курсор над ней намертво запирает скролл.
      plugins.push(window.EmblaCarouselWheelGestures());
    }

    var autoScroll = null;
    if (window.EmblaCarouselAutoScroll && !reduceMotion.matches) {
      autoScroll = window.EmblaCarouselAutoScroll({
        speed: 0.7,
        startDelay: 700,
        stopOnInteraction: false,
        stopOnMouseEnter: true,
        stopOnFocusIn: true
      });
      plugins.push(autoScroll);
    }

    var embla = window.EmblaCarousel(viewport, {
      loop: true,
      dragFree: true,
      align: 'start',
      containScroll: false,
      skipSnaps: true,
      duration: 22
    }, plugins);

    if (!controls) return;

    var prev = makeButton('Предыдущий экран', ICONS.prev);
    var next = makeButton('Следующий экран', ICONS.next);
    prev.addEventListener('click', function () { embla.scrollPrev(); });
    next.addEventListener('click', function () { embla.scrollNext(); });
    controls.appendChild(prev);
    controls.appendChild(next);

    /* Автопрокрутку обязана останавливать видимая кнопка — иначе нарушается
       WCAG 2.2.2: stopOnMouseEnter спасает мышь, но не клавиатуру. */
    if (autoScroll) {
      var toggle = makeButton('Остановить прокрутку', ICONS.pause + ICONS.play);
      toggle.dataset.playing = 'true';

      var sync = function () {
        var api = embla.plugins().autoScroll;
        var playing = api ? api.isPlaying() : false;
        toggle.dataset.playing = String(playing);
        $('.visually-hidden', toggle).textContent =
          playing ? 'Остановить прокрутку' : 'Возобновить прокрутку';
      };

      toggle.addEventListener('click', function () {
        var api = embla.plugins().autoScroll;
        if (!api) return;
        if (api.isPlaying()) api.stop(); else api.play();
        sync();
      });

      embla.on('autoScroll:play', sync).on('autoScroll:stop', sync);
      controls.appendChild(toggle);
      sync();
    }

    controls.hidden = false;
  }


  /* --- Движение ------------------------------------------------------------ */

  function buildReveals() {
    var mm = window.gsap.matchMedia();

    mm.add('(prefers-reduced-motion: no-preference)', function () {
      $$('[data-reveal]').forEach(function (el) {
        window.gsap.to(el, {
          opacity: 1,
          y: 0,
          duration: .55,
          ease: 'power2.out',
          scrollTrigger: { trigger: el, start: 'top 85%', once: true }
        });
      });

      $$('[data-reveal-group]').forEach(function (group) {
        var items = Array.prototype.slice.call(group.children);
        if (!items.length) return;

        /* Короткая группа — один триггер и каскад: заголовок, лид и контент
           читаются как один жест. Длинный список (двенадцать релизов, восемь
           вопросов) так нельзя: нижние элементы отработали бы задолго до того,
           как до них доскроллят. Для них batch — каждый оживает, когда входит
           в кадр. */
        if (items.length > 6) {
          window.ScrollTrigger.batch(items, {
            start: 'top 92%',
            once: true,
            onEnter: function (batch) {
              window.gsap.to(batch, {
                opacity: 1, y: 0, duration: .5, ease: 'power2.out', stagger: .06
              });
            }
          });
          return;
        }

        window.gsap.to(items, {
          opacity: 1,
          y: 0,
          duration: .55,
          ease: 'power2.out',
          stagger: .07,
          scrollTrigger: { trigger: group, start: 'top 85%', once: true }
        });
      });

      // Единственный scrub на сайте. Волна — фоновая графика, небольшое
      // смещение читается как глубина; больше 56 px сразу выглядит дёшево.
      var wave = $('.screens__wave');
      var screens = $('.screens');
      if (wave && screens) {
        window.gsap.fromTo(wave,
          { yPercent: -4 },
          {
            yPercent: 4,
            ease: 'none',
            scrollTrigger: { trigger: screens, start: 'top bottom', end: 'bottom top', scrub: .6 }
          });
      }
    });
  }

  function initMotion() {
    if (!has.gsap) return;

    // С этого момента страховочный таймер в <head> уже не снимет .js-anim:
    // анимации точно построятся.
    window.__animReady = true;
    window.gsap.registerPlugin(window.ScrollTrigger);

    if (has.lenis && !reduceMotion.matches) {
      lenis = new window.Lenis({
        autoRaf: false,
        duration: 1.05,
        anchors: { offset: -headerOffset() }
      });

      /* Один кадр на двоих. Два независимых rAF расходятся на кадр, и
         ScrollTrigger начинает считать прогресс по позиции прошлого кадра —
         scrub-анимации дрожат. lagSmoothing(0) убирает встроенную
         компенсацию лага GSAP, которая Lenis не касается. */
      lenis.on('scroll', window.ScrollTrigger.update);
      window.gsap.ticker.add(function (time) { lenis.raf(time * 1000); });
      window.gsap.ticker.lagSmoothing(0);
    }

    buildReveals();

    /* Пересчёт нужен, только если шрифт ещё не подставлен: иначе триггеры
       окажутся смещены на высоту, которую текст добрал при подстановке.
       Библиотеки грузятся после события load, так что картинки к этому
       моменту уже разложены и второй refresh был бы лишней полной
       перекомпоновкой длинной страницы. */
    if (document.fonts && document.fonts.status !== 'loaded') {
      document.fonts.ready.then(function () { window.ScrollTrigger.refresh(); });
    }
  }


  /* --- Запуск --------------------------------------------------------------- */

  /* Шесть вендорных сборок — это 160 КБ, которые браузер разбирает до первой
     отрисовки, если подключить их тегами в <head>. На эмуляции среднего
     телефона это почти секунда, в течение которой страница не отвечает, а
     заголовок первого экрана не нарисован. Поэтому грузим их сами, после
     события load: интерфейс к этому моменту уже работает — меню, подсказки и
     карусель на нативном скролле подняты выше. */
  var VENDORS = [
    '/assets/js/vendor/gsap-3.15.0.min.js',
    '/assets/js/vendor/ScrollTrigger-3.15.0.min.js',
    '/assets/js/vendor/lenis-1.3.26.min.js',
    '/assets/js/vendor/embla-carousel-8.6.0.umd.js',
    '/assets/js/vendor/embla-carousel-auto-scroll-8.6.0.umd.js',
    '/assets/js/vendor/embla-carousel-wheel-gestures-8.1.0.umd.js'
  ];

  function loadScript(src) {
    return new Promise(function (resolve) {
      var el = document.createElement('script');
      el.src = src;
      el.async = false;          // порядок обязателен: ScrollTrigger ищет gsap
      el.onload = resolve;
      el.onerror = function () { resolve(); };  // не роняем остальные
      document.head.appendChild(el);
    });
  }

  function loadVendors() {
    /* Говорим страховочному таймеру из <head>, что загрузка пошла: иначе он
       снимет .js-anim ровно в тот момент, когда библиотеки почти доехали, и
       появления пропадут на ровном месте. Если загрузка всё-таки сорвётся,
       класс снимем сами ниже. */
    window.__animReady = true;

    VENDORS.reduce(function (chain, src) {
      return chain.then(function () { return loadScript(src); });
    }, Promise.resolve()).then(function () {
      refreshFeatures();
      initCarousel();
      initMotion();
      if (!has.gsap) document.documentElement.classList.remove('js-anim');
    });
  }

  function whenIdle(fn) {
    if (window.requestIdleCallback) window.requestIdleCallback(fn, { timeout: 1200 });
    else setTimeout(fn, 200);
  }

  // Сначала — всё, что написано на голом DOM и должно работать немедленно.
  unhideAboveFold();
  initHeaderState();
  initBurger();
  initDownloadMenu();
  initDisclosures();
  initSkipLink();

  if (document.readyState === 'complete') whenIdle(loadVendors);
  else window.addEventListener('load', function () { whenIdle(loadVendors); });
})();
