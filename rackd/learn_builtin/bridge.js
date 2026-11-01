/* Мост модуля «Обучение» с Rack Live. Модуль работает в изолированном окне без доступа к сети и к Rack Live; единственное, что ему доступно, —
   прочитать и сохранить СВОЙ прогресс. Подключение: <script src="/api/learn/bridge.js"></script>
   RLLearn.load() → Promise<объект>   (то, что сохранили раньше, или {})
   RLLearn.save(объект) → Promise<объект>   (список "done" только пополняется: отметки из других вкладок не затираются; размер до 64 КБ) */
(function () {
  var seq = 0, wait = {};
  function call(type, data) {
    return new Promise(function (resolve, reject) {
      var id = ++seq;
      wait[id] = { resolve: resolve, reject: reject };
      parent.postMessage({ rl: 'learn', id: id, type: type, data: data }, '*');
      setTimeout(function () { if (wait[id]) { delete wait[id]; reject(new Error('Rack Live не ответил')); } }, 10000);
    });
  }
  addEventListener('message', function (e) {
    var m = e.data;
    if (e.source !== parent || !m || m.rl !== 'learn-re' || !wait[m.id]) return;
    var w = wait[m.id]; delete wait[m.id];
    if (m.ok) w.resolve(m.data); else w.reject(new Error(m.error || 'ошибка'));
  });
  window.RLLearn = { load: function () { return call('load'); }, save: function (d) { return call('save', d); } };
})();
