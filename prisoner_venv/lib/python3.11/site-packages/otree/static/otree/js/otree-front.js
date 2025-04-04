/*!
otree-front v2.0.1b3
Microframework for interactive pages for oTree platform
(C) qwiglydee@gmail.com
https://github.com/oTree-org/otree-front
*/
var otc = (function (exports) {
    'use strict';

    /**
     * Check if an arg is Array
     */
    function isArray(o) {
      return Array.isArray(o);
    }

    /**
     * Check if an arg is Function
     */
    function isFunction(obj) {
      return typeof obj == "function";
    }

    /**
     * Check if an arg is void (null, undefined or NaN)
     */
    function isVoid(value) {
      return value === undefined || value === null || Number.isNaN(value);
    }

    /**
     * Check if an arg is a scalar value
     *
     * from https://github.com/oleics/node-is-scalar
     */
    function isScalar(value) {
      var type = typeof value;
      if (type === 'string') return true;
      if (type === 'number') return true;
      if (type === 'boolean') return true;
      if (type === 'symbol') return true;
      if (value == null) return true;
      if (value instanceof Symbol) return true;
      if (value instanceof String) return true;
      if (value instanceof Number) return true;
      if (value instanceof Boolean) return true;
      return false;
    }

    /*
     * is-plain-object <https://github.com/jonschlinkert/is-plain-object>
     *
     * Copyright (c) 2014-2017, Jon Schlinkert.
     * Released under the MIT License.
     */

    function isObject(o) {
      return Object.prototype.toString.call(o) === '[object Object]';
    }

    /**
     * Check if an arg is a plain object (not a class instance)
     */
    function isPlainObject(o) {
      var ctor, prot;
      if (isObject(o) === false) return false;

      // If has modified constructor
      ctor = o.constructor;
      if (ctor === undefined) return true;

      // If has modified prototype
      prot = ctor.prototype;
      if (isObject(prot) === false) return false;

      // If constructor does not have an Object-specific method
      if (prot.hasOwnProperty('isPrototypeOf') === false) {
        return false;
      }

      // Most likely a plain Object
      return true;
    }

    function matchType(value, type) {
      switch (type) {
        case 'any':
          return true;
        case 'array':
          return isArray(value);
        case 'object':
          return isObject(value);
        case 'class':
          return isFunction(value);
        default:
          return typeof value === type;
      }
    }
    function matchTypes(args, types) {
      return Array.from(args).every((a, i) => matchType(a, types[i]));
    }
    function assertArgs(fname, args) {
      for (var _len = arguments.length, types = new Array(_len > 2 ? _len - 2 : 0), _key = 2; _key < _len; _key++) {
        types[_key - 2] = arguments[_key];
      }
      let matching = types.filter(argtypes => argtypes.length == args.length && matchTypes(args, argtypes));
      if (matching.length == 0) {
        const usage = types.map(argtypes => "".concat(fname, "(").concat(argtypes.join(", "), ")")).join(" or ");
        throw new Error("Invalid arguments, expected: ".concat(usage));
      }
    }

    /**
     * Utils to work with dot-separated key paths
     */


    /** scan through ancestors
     *
     * yields paths of ancestors + inner relative path
     *
     * scan("foo.bar.baz") => ["foo", "bar.baz"], ["foo.bar", "baz"]
     */
    function* scan(strpath) {
      let path = strpath.split('.');
      for (let i = 0; i < path.length - 1; i++) {
        yield [path.slice(0, i + 1).join("."), path.slice(i + 1).join(".")];
      }
    }

    /** extract nested value
     *
     * returns undefined if path is unreachable
     */
    function extract(obj, path) {
      if (typeof path == "string") path = path.split(".");
      return path.reduce((o, k) => o && k in o ? o[k] : undefined, obj);
    }

    /* if the value is worth spanshotting */
    function isValuable(value) {
      return isScalar(value) || isObject(value) || isArray(value) || value instanceof HTMLElement;
    }

    /* if the value needs recursion */
    function isCompound(value) {
      return isPlainObject(value) || isArray(value);
    }

    /* yields all items recursively as [varpath, value|null] */
    function flatten(obj) {
      let prefix = arguments.length > 1 && arguments[1] !== undefined ? arguments[1] : "";
      return function* () {
        // yield value, including compound, except top-level
        if (prefix != "" && isValuable(obj)) {
          yield [prefix, isVoid(obj) ? null : obj];
        }

        // recurse into compound
        if (isCompound(obj)) {
          for (let [k, v] of Object.entries(obj)) {
            if (isValuable(v)) yield* flatten(v, prefix ? "".concat(prefix, ".").concat(k) : k);
          }
        }
      }();
    }

    /**
     * Map of changes in page vars.
     *
     * The map keys are var names (without `vars.` prefix) and values are their new values.
     * If a value has been deleted, the associated value in the map is `null`
     *
     * For complex objects their fields are stored as dot-paths like `obj.field` or `obj.subobj.field`
     *
     * @hideconstructor
     */
    class Changes extends Map {
      /**
       * Check if the changeset affects a var or a field
       *
       * When whole object is replaced, that implies all nested fields are affected.
       *
       * To check if ay fields changed, use "obj.*"
       *
       * @example
       * ot.onEvent('update', function(e) {
       *   let changes = e.detail.changes;
       *   if (changes.affect("progress.total_score")) { ... }
       * })
       *
       * @param {string} varpath a var or a field reference
      */
      affect(varpath) {
        let wild = varpath.endsWith(".*");
        let key = wild ? varpath.slice(0, -2) : varpath;

        // direct match
        if (this.has(key)) return true;

        // scan ancestors
        for (let [head, tail] of scan(key)) {
          if (this.has(head)) return true;
        }

        // scan descendants
        if (wild) {
          let keysub = key + ".";
          for (let k of this.keys()) {
            if (k.startsWith(keysub)) return true;
          }
        }
        return false;
      }

      /**
       * Extract updated value
       *
       * This extracts new value from the changeset.
       *
       * @param {string} varpath a var or a field reference
       */
      extract(varpath) {
        let key = varpath.endsWith(".*") ? varpath.slice(0, -2) : varpath;

        // direct match
        if (this.has(key)) return this.get(key);

        // scan ancestors
        for (let [head, tail] of scan(key)) {
          if (this.has(head)) return extract(this.get(head), tail);
        }
      }
    }

    /**
     * Snapshot an object
     *
     * Create a flat map of all fields and nested fields.
     *
     * @returns {Map} of { varpath -> value }
     * @ignore
     */
    function snap(obj) {
      return new Map(flatten(obj));
    }

    /**
     * Compares two snapshots
     *
     * @returns {Changes}
     * @ignore
     */
    function diff(oldshot, newshot) {
      let allkeys = new Set([].concat(Array.from(oldshot.keys()), Array.from(newshot.keys())));
      let changed = Array.from(allkeys).filter(k => oldshot.get(k) !== newshot.get(k));

      // filter out inner keys of changed parents
      function parents(path) {
        return Array.from(scan(path)).map(a => a[0]);
      }
      changed = changed.filter(k => !parents(k).some(p => changed.includes(p)));

      // create map with nulls for missing
      return new Changes(changed.map(k => [k, newshot.has(k) ? newshot.get(k) : null]));
    }

    /**
     * All dynamic content is stored in a global object `vars`.
     * The object may contain either scalar values like `vars.counter = 42`
     * or a complex nested objects like `vars.progress = { total: ..., completed: ..., score: ... }`
     *
     * The `vars` are totally different from `js_vars` and `vars_for_template`.
     * They only exist while on-page scripts are running.
     * They should be initialized from some event handlers (like `ot.onEvent('loaded', function startGame() { vars.something = ... })`)
     *
     * When a page is submitted or reloaded, all the data in the `vars` is lost.
     * To save the data, it should be send to server via live socket in real time,
     * or it could be inserted into form fields (like, `<input type="hidden" name="something" ot-value="vars.something">`,
     *
     * Changes in the `vars` are automatically or almost-automatically detected
     * and broadcasted to all page components like directives and handlers.
     *
     * @module vars
     */


    /**
     * Indicates that some of page vars have been changed.
     *
     * The event is generated automatically after each other event handler executed
     *
     * @event update
     * @prop {object} detail
     * @prop {Changes} detail.changes map of all changed vars and object fields
     */

    /**
     * Check for updates.
     *
     * Track changes in page vars and generate `update` event to refresh directives and stuff.
     *
     * This is usually called automatically.
     *
     * In some cases it needs to be called explicitely:
     * - calling normal funcions from some async handlers
     * - updating `vars` from some foreign handler installed by other means (like, `addEventListener` or jQuery)
     * - debugging from console
     *
     * @fires update
     */
    function updatePage() {
      let newsnap = snap(window.vars);
      let changes = diff(window.ot_snapshot, newsnap);
      if (changes.size) {
        window.ot_snapshot = newsnap;
        document.body.dispatchEvent(new CustomEvent("ot.update", {
          detail: {
            changes
          }
        }));
      }
    }
    function initVars() {
      window.vars = {};
      window.ot_snapshot = new Map();
    }

    /**
     * The main means of control execution flow in the framework are events and handlers.
     * The events indicate something important happened on the page,
     * and handlers are functions that react to the events and perform some useful actions.
     *
     * The framework uses browser built-in events' machinery.
     *
     * Events specific to the framework (described as 'page events') have internal type like `ot.something` and carry useful data in `event.detail`.
     * They are triggered and handled globally, and not related to any particular html element.
     *
     * The utils in this module only deal with ot-events and refer to them without the `ot.` prefix.
     * The utils cannot handle any native events, such as `click` or `mousemove`.
     * I.e. `emitEvent('click'); onEvent('click', handle)` deal with page event `ot.click` and not native browser event 'click'.
     *
     * @module events
     */


    /**
     * A function to handle event.
     *
     * After a handler executed, the framework automatically checks if any `vars` are changed and generates `update` event.
     *
     * A handler could be `async` and contain some `await`s.
     *
     * To access data carried with an event, a handler should unpack it from the `event.detail`.
     *
     * @example
     * ot.onEvent('timer', handleTimer)
     *
     * function handleTimer(event) {
     *   let { name, count, elapsed } = event.detail;
     *   // ...
     * }
     *
     * @callback eventHandler
     * @param {Event} event
     */

    /**
     * Event matcher
     *
     * A function to check if an event matches some particular criteria.
     *
     * A corresponding handler is only executed when the matcher returns true.
     *
     * @callback eventMatcher
     * @param {Event} event
     */

    /**
     * Install a handler for a page event.
     *
     * The `handler` is to be called whenever an event of specific type and condition is generated.
     *
     * If a `matcher` is specified as a string, the handler is only called when the `event.detail.name` matches.
     * If a `matcher` is a function, the handler is only called when the function returns true
     *
     * When multiple handlers are installed for the same event type - they all will be called, in order of installation.
     *
     * @example
     * ot.onEvent('timer', handleTimer);
     * ot.onEvent('input', 'answer', handleAnswer);
     * ot.onEvent('update', (event) => event.detail.changes.affect("myvar"), handleVarChange);
     *
     * @param {string} type type of events to handle
     * @param {string|eventMatcher} [matcher] a name or a function
     * @param {eventHandler} handler
     */
    function onEvent(type, matcher, handler) {
      assertArgs("onEvent", arguments, ['string', 'function'], ['string', 'string', 'function'], ['string', 'function', 'function']);
      if (arguments.length == 2) {
        handler = arguments[1];
        matcher = null;
      } else if (typeof arguments[1] == 'string') {
        matcher = e => e.detail && e.detail.name == arguments[1];
      }
      document.body.addEventListener("ot.".concat(type), async event => {
        if (matcher && !matcher(event)) return;
        await handler.call(null, event);
        if (type !== 'update') updatePage();
      });
    }

    /**
     * Emit a page event.
     *
     * Generate an event and queue its handling.
     *
     * @param {string} type type of event to generate
     * @param {object} [detail] some data to attach to the event
     */
    function emitEvent(type, detail) {
      assertArgs("emitEvent", arguments, ['string'], ['string', 'object']);
      setTimeout(() => document.body.dispatchEvent(new CustomEvent("ot.".concat(type), {
        detail
      })));
    }

    /**
     * Delay a page event.
     *
     * Generate an event after specified time.
     *
     * @param {number} delay delay in ms
     * @param {string} type type of event to generate
     * @param {object} [detail] some data to attach to the event
     */
    function delayEvent(time, type, detail) {
      assertArgs("delayEvent", arguments, ['number', 'string'], ['number', 'string', 'object']);
      setTimeout(() => document.body.dispatchEvent(new CustomEvent("ot.".concat(type), {
        detail
      })), time);
    }

    /**
     * Trigger an event.
     *
     * Generate an event and trigger it immediately.
     * All handlers are called without waiting queue.
     *
     * @param {string} type type of event to generate
     * @param {object} [detail] some data to attach to the event
     */
    function triggerEvent(type, detail) {
      assertArgs("triggerEvent", arguments, ['string'], ['string', 'object']);
      document.body.dispatchEvent(new CustomEvent("ot.".concat(type), {
        detail
      }));
    }

    /** @module */


    /**
     * Indicates that the page has been just loaded (or reloaded).
     *
     * Triggered after everything has been initialized.
     *
     * Typical usage:
     * - initialize global page vars
     * - start the game
     *
     * @event loaded
     */

    /**
     * Indicates that the page is being submitted.
     *
     * Triggered by a submit-button or submitPage()
     *
     * If the page form already has some invalid fields, the event won't even be triggered (neither by button nor by submitPage).
     * If its handler invalidates some fields, submition is canceled.
     *
     * Typical usage:
     * - update some vars to put into hidden fields, via `ot-value`
     * - invalidate some fields to block submission
     *
     * Note: disabled inputs are not submitted, use ot.enableInputs to explicitely form fields.
     *
     * @example
     * <input id="field-foo" type="hidden" name="foo" ot-value="vars.foo">
     * <input id="field-bar" type="hidden" name="bar" ot-value="vars.bar">
     *
     * ot.onEvent('submitted', submitFields);
     *
     * function submitFields() {
     *   ot.enableInputs("field-*");
     *   vars.foo = ...;
     *   vars.bar = ...;
     * }
     *
     * @event submitted
     */

    function initPage() {
      document.getElementById("form").addEventListener("submit", onSubmit);
    }
    function onSubmit(event) {
      // immediately call handler
      triggerEvent("submitted");

      // block default submission
      event.preventDefault();
      // delay submition to let vars update
      if (document.getElementById("form").checkValidity()) {
        setTimeout(() => submitForm());
      }
    }
    function startPage() {
      triggerEvent("loaded");
    }

    /**
     * Submit page.
     *
     * Equivalent of pressing a submit button "next".
     *
     * This triggers event 'submitted' and corrsponding handler.
     */
    function submitPage() {
      // this simulates submit button, including 'submit' event
      document.getElementById("form").requestSubmit();
    }

    /**
     * Complete page immediately.
     *
     * Similar to `submitPage` but does not trigger `submitted` event
     */
    function completePage() {
      submitForm();
    }

    /**
     * Submit page immediately, without 'submit' event
     */
    function submitForm() {
      // using prototype because form.submit can be screened by an input with id=submit
      HTMLFormElement.prototype.submit.call(document.getElementById("form"));
    }

    /**
     * Tools to select elements with checking
     */
    function byId(id) {
      return "#".concat(id);
    }
    function byPref(patt) {
      return "[id^=".concat(patt.slice(0, -1), "]");
    }
    function byName(name) {
      return "[name=".concat(name, "]");
    }
    function byIdName(ref) {
      return "".concat(byName(ref), ",").concat(byId(ref));
    }
    function byPtrnId(ref) {
      return ref.endsWith("*") ? byPref(ref) : byId(ref);
    }
    function byPtrnIdName(ref) {
      return ref.endsWith("*") ? byPref(ref) : byIdName(ref);
    }

    /* selecting with checking and error reporting */
    function _select(selFn, ref) {
      let selector = selFn(ref);
      let selected = document.querySelectorAll(selector);
      if (!selected.length) throw Error("No elements found for: ".concat(ref));
      return Array.from(selected);
    }

    /**
     * select item or array with checking
     *
     * @param {function} selFn function to convert ref to css selector
     * @param {array|string} ref id, name or id-pattern
     * @return {array} selection: [ [selector, element], ... ]
     */
    function select(selFn, refs) {
      if (!isArray(refs)) refs = [refs];
      return refs.map(ref => _select(selFn, ref)).flat();
    }

    /**
     * selects all inputs
     * @return {array} selection: [ [null, element], ... ]
     */
    function selectInputs() {
      return Array.from(document.querySelectorAll("[name]"));
    }

    /**
     * Test if an element is native html input field
     *
     * @param {HTMLElement} elem element object
     * @return {boolean}
     */
    function isElemField(elem) {
      return elem instanceof HTMLInputElement || elem instanceof HTMLTextAreaElement || elem instanceof HTMLSelectElement;
    }

    /**
     * Test if an element is a navigable field/widget by tab
     *
     * @param {HTMLElement} elem element object
     * @return {boolean}
     */
    function isElemNavigable(elem) {
      return elem.tabIndex != -1;
    }

    /**
     * Test if an element is text editable field
     *
     * @param {HTMLElement} elem element object
     * @return {boolean}
     */
    function isElemEditable(elem) {
      return ["text", "textarea", "email", "tel", "date", "time", "datetime-local", "url", "number"].includes(elem.type);
    }

    /**
     * Test if an element is a checkable field
     *
     * @param {HTMLElement} elem element object
     * @return {boolean}
     */
    function isElemCheckable(elem) {
      return ["radio", "checkbox"].includes(elem.type);
    }

    /**
     * Add `hidden` attribute to an element
     *
     * @param {HTMLElement} elem element object
     */
    function hideElem(elem) {
      elem.setAttribute("hidden", "");
    }

    /**
     * Remove `hidden` attribute from an element
     *
     * @param {HTMLElement} elem element object
     */
    function showElem(elem) {
      elem.removeAttribute("hidden");
    }

    /**
     * Add `disabled` attribute to an element
     *
     * @param {HTMLElement} elem element object
     */
    function disableElem(elem) {
      elem.setAttribute("disabled", "");
    }

    /**
     * Remove `disabled` attribute from an element
     *
     * @param {HTMLElement} elem element object
     */
    function enableElem(elem) {
      elem.removeAttribute("disabled");
    }

    /**
     * ## Switching utils.
     *
     * Utilities to toggle fragments of a page or inputs.
     *
     * Elements on a page are identified by standard html attribute `id`, like `<section id="section1">`.
     * The `id` should be unique across a page for each element and input.
     *
     * Elements can also be grouped by ids with hyphen like `<p id="feedback-success">`.
     * They can be referenced all in once by "feedback-*".
     *
     * Inputs can be referenced either by ids or by names, like `<input type="text" name="foo">`.
     * The name should not be unique and may reused in different inputs such as choices.
     *
     * @module
     */

    function apply$1(selection, fn) {
      return selection.forEach(elem => fn(elem));
    }

    /**
     * Hide a html fragment.
     *
     * @param {string} id html id of an element
     */
    function hideDisplay(id) {
      assertArgs("hideDisplay", arguments, ['string']);
      let selected = select(byId, id);
      apply$1(selected, hideElem);
    }

    /**
     * Hide multiple html fragments.
     *
     * @param {array|string} ids an array of ids or an id-pattern like `something-*`
     */
    function hideDisplays(ids) {
      assertArgs("hideDisplays", arguments, ['string'], ['array']);
      let selected = select(byPtrnId, ids);
      apply$1(selected, hideElem);
    }

    /**
     * Show a previously hidden html fragment.
     *
     * @param {string} id html id of an element
     */
    function showDisplay(id) {
      assertArgs("showDisplay", arguments, ['string']);
      let selected = select(byId, id);
      apply$1(selected, showElem);
      autofocus(selected);
    }

    /**
     * Show multiple previously hidden html fragments.
     *
     * @param {string|array} ids an array of ids or an id-pattern like `something-*`
     */
    function showDisplays(ids) {
      assertArgs("showDisplays", arguments, ['string'], ['array']);
      let selected = select(byPtrnId, ids);
      apply$1(selected, showElem);
      autofocus(selected);
    }

    /**
     * Disable an input.
     *
     * @param {string} id_or_name an id or name of an input
     */
    function disableInput(id_or_name) {
      assertArgs("disableInput", arguments, ['string']);
      let selected = select(byIdName, id_or_name);
      apply$1(selected, disableElem);
    }

    /**
     * Disable multiple inputs.
     *
     * @param {string|array} [ids_or_names] list of ids, names or an id-pattern like `something-*`, by default - all inputs
     */
    function disableInputs(ids_or_names) {
      assertArgs("disableInputs", arguments, ['string'], ['array'], []);
      let selected = ids_or_names === undefined ? selectInputs() : select(byPtrnIdName, ids_or_names);
      apply$1(selected, disableElem);
    }

    /**
     * Enable a previously disabled input.
     *
     * @param {string} id_or_name an id or name of an input
     */
    function enableInput(id_or_name) {
      assertArgs("enableInput", arguments, ['string']);
      let selected = select(byIdName, id_or_name);
      let disabled = selected.filter(e => e.matches("[disabled]"));
      apply$1(selected, enableElem);
      autofocus(disabled);
    }

    /**
     * Enable multiple previously disabled inputs.
     *
     * @param {string|array} [ids_or_names] list of ids, names or an id-pattern like `something-*`, by default - all inputs
     */
    function enableInputs(ids_or_names) {
      assertArgs("enableInputs", arguments, ['string'], ['array'], []);
      let selected = ids_or_names === undefined ? selectInputs() : select(byPtrnIdName, ids_or_names);
      let disabled = selected.filter(e => e.matches("[disabled]"));
      apply$1(selected, enableElem);
      autofocus(disabled);
    }
    function autofocus(affected) {
      let autofocusing;

      // re-enabled inputs
      autofocusing = affected.find(e => e.matches("[autofocus]:not([disabled])"));
      if (autofocusing) {
        autofocusing.focus();
        return;
      }

      // nested in un-hidden
      autofocusing = affected.map(e => Array.from(e.querySelectorAll("[autofocus]:not([disabled])"))).flat();
      if (autofocusing.length) {
        autofocusing[0].focus();
        return;
      }
    }

    /**
     * Timers.
     *
     * Utilities to implement time-based mechanics.
     *
     * A timer is a source of time-based events, and it can generate one or more scheduled events.
     * Multiple timers can be used, differentiated by their names.
     *
     * When re-scheduling events with the same timer name, all previously scheduled events are canceled.
     *
     * **CAUTION**: When a page is reloaded amid a game process - all the timers lose their state (counter and elapsed time).
     *
     * @module
     */


    /**
     * Timer event.
     *
     * An event generated by timers.
     *
     * @event timer
     * @prop {object} detail
     * @prop {string} detail.name timer name
     * @prop {number} detail.elapsed time elapsed since it's started
     * @prop {number} detail.count counter for recurring events, 0 for immediate iteration
     */

    class Timer {
      constructor(name) {
        this.name = name;
        this.started = 0;
        this.counter = 0;
        this.handler = null;
      }
      start() {
        this.started = Date.now();
        this.counter = 0;
        window.ot_timers[this.name] = this;
      }
      elapsed() {
        return Date.now() - this.started;
      }
      cancel() {
        window.clearTimeout(this.handler);
        delete window.ot_timers[this.name];
      }
    }
    class TimeoutTimer extends Timer {
      constructor(name, timeout) {
        super(name);
        this.timeout = timeout;
      }
      start() {
        super.start();
        this.handler = window.setTimeout(() => {
          triggerEvent("timer", {
            name: this.name,
            elapsed: this.elapsed(),
            count: 1
          });
        }, this.timeout);
      }
    }
    class PeriodicTimer extends Timer {
      constructor(name, period, count) {
        super(name);
        this.period = period;
        this.count = count;
      }
      start() {
        super.start();
        this.handler = window.setTimeout(() => {
          triggerEvent("timer", {
            name: this.name,
            elapsed: this.elapsed(),
            count: 0
          });
          this.restart();
        }, 0);
      }
      restart() {
        this.handler = window.setInterval(() => {
          this.counter += 1;
          triggerEvent("timer", {
            name: this.name,
            elapsed: this.elapsed(),
            count: this.counter
          });
          if (this.count && this.counter >= this.count) {
            this.cancel();
          }
        }, this.period);
      }
    }
    class SequenceTimer extends Timer {
      constructor(name, intervals, customData) {
        super(name);
        this.intervals = intervals;
        this.customData = customData;
      }
      start() {
        super.start();
        this.handler = window.setTimeout(() => {
          triggerEvent("timer", {
            name: this.name,
            elapsed: this.elapsed(),
            count: 0,
            customData: this.customData
          });
          this.restart();
        }, 0);
      }
      restart() {
        let segmentDuration = this.intervals[this.counter];
        // allow people to set a segment duration to null, useful for debugging
        //console.log({segmentDuration})
        if (segmentDuration == null) return;
        this.handler = window.setTimeout(() => {
          this.counter += 1;
          triggerEvent("timer", {
            name: this.name,
            elapsed: this.elapsed(),
            count: this.counter,
            customData: this.customData
          });
          if (this.counter >= this.intervals.length) {
            this.cancel();
          } else {
            this.restart();
          }
        }, segmentDuration);
      }
    }
    function initTimers() {
      window.ot_timers = {};
    }

    /**
     * Schedule a timer event after specified timeout.
     *
     * @param {string} name timer name
     * @param {number} timeout period of time
     */
    function startTimer(name, timeout) {
      assertArgs("startTimer", arguments, ['string', 'number']);
      cancelTimer(name);
      new TimeoutTimer(name, timeout).start();
    }

    /**
     * Schedule a ыуйгутсу of periodic events with a specified period.
     *
     * Each event will have incrementing `count`, and cumulative `elapsed` time.
     * The first iteration triggers immediatetly after scheduling, with count=0.
     *
     * @param {string} name timer name
     * @param {number} period period of time
     * @param {number} [max_count] max number of iterations, default = infinite
     */
    function startTimerPeriodic(name, period, max_count) {
      //console.log(arguments);
      assertArgs("startTimerPeriodic", arguments, ['string', 'number', 'number'], ['string', 'number']);
      cancelTimer(name);
      new PeriodicTimer(name, period, max_count).start();
    }

    /**
     * Schedule a sequence of events at specified time moments.
     *
     * Each event will have incrementing `count`, and cumulative `elapsed` time.
     *
     * @param {string} name timer name
     * @param {number[]} intervals intervals
     */
    function startTimerSequence(name, intervals) {
      let customData = arguments.length > 2 && arguments[2] !== undefined ? arguments[2] : {};
      assertArgs("startTimerSequence", arguments, ['string', 'array'], ['string', 'array', 'object']);
      cancelTimer(name);
      new SequenceTimer(name, intervals, customData).start();
    }

    /**
     * Cancel a timer and all its scheduled events.
     *
     * @param {string} name timer name
     */
    function cancelTimer(name) {
      assertArgs("cancelTimer", arguments, ['string']);
      if (name in window.ot_timers) window.ot_timers[name].cancel();
    }

    /**
     * Cancel multiple timers, or all started timers, and all their scheduled events.
     *
     * @param {string|string[]} [name] a name or a list of names, by default - all started timers
     */
    function cancelTimers(names) {
      assertArgs("cancelTimers", arguments, [], ['string'], ['array']);
      if (names === undefined) names = Array.from(Object.keys(window.ot_timers));
      if (!isArray(names)) names = [names];
      for (let n of names) cancelTimer(n);
    }

    /**
     * ## Time measurement tools
     *
     * The measurement is performed in browser and not affected by any network latency.
     * Measurements are rounded to precision of 1 millisecond.
     *
     * You can take several measurements using different measurement names.
     *
     * **CAUTION**: When a page is reloaded amid a game process - all measurements get lost.
     *
     * @module
     */

    function begin(tag) {
      window.performance.mark("ot.".concat(tag, ".begin"));
    }
    function mark(tag) {
      window.performance.mark("ot.".concat(tag));
    }
    function measure(tag) {
      return window.performance.measure("ot.".concat(tag, ".measure"), "ot.".concat(tag, ".begin"), "ot.".concat(tag));
      // return performance.getEntriesByName(`otree.${tag}.measure`).slice(-1)[0];
    }

    function clear(tag) {
      window.performance.clearMarks("ot.".concat(tag, ".begin"));
      window.performance.clearMarks("ot.".concat(tag));
      window.performance.clearMeasures("ot.".concat(tag, ".measure"));
    }

    /**
     * Begin time measurement.
     *
     * Mark a moment of time from which time is to be measured.
     *
     * @param {string} [tag] a name to differentiate multiple measurements
     */
    function beginTimeMeasurement() {
      let tag = arguments.length > 0 && arguments[0] !== undefined ? arguments[0] : "measurement";
      assertArgs("beginTimeMeasurement", arguments, [], ['string']);
      clear(tag);
      begin(tag);
    }

    /**
     * Get time measurement.
     *
     * Measure time passsed from the moment when measurement begun.
     *
     * You can take the measurement several times, and they will be measured from the same moment.
     *
     * @param {string} [tag] a name to differentiate multiple measurements
     * @return {number} time passed in milliseconds
     */
    function getTimeMeasurement() {
      let tag = arguments.length > 0 && arguments[0] !== undefined ? arguments[0] : "measurement";
      assertArgs("getTimeMeasurement", arguments, [], ['string']);
      mark(tag);
      return Math.round(measure(tag).duration);
    }

    /**
     * ## Image preloading tools
     *
     * @module
     */


    /**
     * Preload single image.
     *
     * Request an image by its url and wait until it's downloaded.
     * This puts the image into browser cache and reduce loading time when an `<img ot-src=url>` is updated.
     *
     * The function returns loaded image (a html element detached from page), although you have nothing useful to do with it.
     *
     * **NOTE**: The caching mechanics may be broken by configuration of a browser or a server that hosts images.
     * Preloading images doesn't guarantee there will be no delay time.
     *
     * @see {@link [ot-src]}
     *
     * @example
     * <img ot-src="vars.trial.image_url">
     *
     * @example
     * async function startTrial() {
     *   await ot.preloadImage(vars.trial.image_url);
     *   // ...
     * }
     *
     * @param {string} url of an image
     * @async
     * @return {Promise<Image>} loaded image
     */
    function preloadImage(url) {
      assertArgs("preloadImage", arguments, ['string']);
      return new Promise((resolve, reject) => {
        let img = new Image();
        img.loading = "eager";
        img.src = url;
        img.onload = () => resolve(img);
      });
    }

    /**
     * Preload multiple images.
     *
     * Request a list of images by its url and wait until all of them are downloaded.
     *
     * @see preloadImage
     * @param {string[]} url of an image
     * @async
     * @return {Promise<Image[]>} loaded image
     */
    function preloadImages(urls) {
      assertArgs("preloadImage", arguments, ['array']);
      return Promise.all(urls.map(url => preloadImage(url)));
    }

    /** @module */


    /**
     * Delay execution for specified amount of time.
     * Page is automatically updated before delay.
     *
     * It can be used to implement some animation-like bevaviour with interleaved stages.
     *
     * **CAUTION**: During the pause, other scripts can run and can mess up with variables.
     *
     * @example
     * ot.onEvent('something', handleSomething);
     *
     * // updates vars.foo 3 times with pauses
     * async function handleSomething() {
     *    vars.foo = 1;
     *    await ot.delay(500);
     *    vars.foo = 2;
     *    await ot.delay(500);
     *    vars.foo = 3;
     * }
     *
     * @param {number} time delay in ms
     * @async
     */
    async function delay(time) {
      updatePage();
      return new Promise((resolve, reject) => {
        window.setTimeout(() => resolve(), time);
      });
    }

    function apply(selection, fn) {
      return selection.forEach(elem => fn(elem));
    }
    function resetElem(elem) {
      if (isElemCheckable(elem)) {
        elem.checked = elem.defaultChecked;
      } else {
        elem.value = elem.defaultValue;
      }
      elem.dispatchEvent(new Event('ot.reset'));
    }
    function commitElem(elem) {
      elem.dispatchEvent(new Event('ot.commit'));
    }

    /**
     * Reset inputs to their initial state.
     *
     * The initial value is taken from `value` attribute, or whatever a custom directive initialized.
     * For checkboxes and radio it operates on checked state and `checked` attribute.
     *
     * If the value is not actually changed, widgets would be notified anyway.
     *
     * It works on any form fields, or any element that looks like an input (having 'name' attribute).
     *
     * @memberof directives
     * @param {array} [names] names of inputs to reset, by default - all inputs
     */
    function resetInputs(names) {
      assertArgs("resetInputs", arguments, [], ["array"]);
      let selected = names === undefined ? selectInputs() : select(byName, names);
      apply(selected, resetElem);
    }

    /**
     * Reset a specific input to its initial state.
     *
     * @see resetInputs
     *
     * @memberof directives
     * @param {string} name name of an input
     */
    function resetInput(name) {
      assertArgs("resetInput", arguments, ['string']);
      let selected = select(byName, name);
      apply(selected, resetElem);
    }

    /**
     * Commit specified input.
     *
     * Request an ot-input or a custom widget to generate `input` event with its current value.
     *
     * This won't work on bare form fields without ot-input extension.
     *
     * @memberof directives
     * @param {string} name name of an input
     * @emits directives.input
     */
    function commitInput(name) {
      assertArgs("commitInput", arguments, ['string']);
      let linked = document.querySelectorAll("[input=".concat(name, "]"));
      let named = document.querySelectorAll("[name=".concat(name, "]"));
      if (linked.length) {
        apply(linked, commitElem);
      } else if (named.length) {
        apply(named, commitElem);
      } else {
        throw Error("No inputs found: ".concat(name));
      }
    }

    function _defineProperty(obj, key, value) {
      key = _toPropertyKey(key);
      if (key in obj) {
        Object.defineProperty(obj, key, {
          value: value,
          enumerable: true,
          configurable: true,
          writable: true
        });
      } else {
        obj[key] = value;
      }
      return obj;
    }
    function _toPrimitive(input, hint) {
      if (typeof input !== "object" || input === null) return input;
      var prim = input[Symbol.toPrimitive];
      if (prim !== undefined) {
        var res = prim.call(input, hint || "default");
        if (typeof res !== "object") return res;
        throw new TypeError("@@toPrimitive must return a primitive value.");
      }
      return (hint === "string" ? String : Number)(input);
    }
    function _toPropertyKey(arg) {
      var key = _toPrimitive(arg, "string");
      return typeof key === "symbol" ? key : String(key);
    }

    /**
     * Base class for all directives.
     *
     * Defines main API and facilities to create built-in and custom directives.
     *
     * Generic lifecycle of a directive (implemented in other classes, not in base though):
     * - `attachDirective(class, selector)` is called to create directives on html elements
     *   - `init()` is called
     *   - `render()` is optionally called from init
     * - some page variables change
     *   - `update()` is called if some changed vars are referenced by params
     *   - `render()` is optionally called from update
     * - some interaction happens
     *   - whatever handlers setup in init like `onSomething` are called
     * - internal value of input is changed by browser interaction, or by `resetInputs`
     *   - `update()` is called indicating that `value` has been changed
     *   - `render()` is optionally called from update
     *   - `commit()` is called to signal 'input' event (but not for reset)
     *
     * For custom widgets with dynamic content and inputs use `WidgetDirective`.
     *
     * @property {ParamsConfig} params class-level definition of mapping attributes to properties
     * @property {HTMLElemet} elem the host element to which the directive is attached
     * @hideconstructor
     */
    class DirectiveBase {
      constructor(elem) {
        _defineProperty(this, "params", {});
        this.elem = elem;
      }

      /**
       * Indicates that the element or some of its ancestor is hidden by attribute `hidden`.
       * (actual visibility may be redefined by css rules)
       */
      get hidden() {
        return this.elem.hasAttribute('hidden') || this.elem.closest("[hidden]") != null;
      }

      /**
       * Indicates that the element is disabled (by attribute 'disabled')
       * (also applies to non-input directives)
       */
      get disabled() {
        return this.elem.hasAttribute('disabled');
      }

      /**
       * Indicates that the element has focus like a form field
       */
      get focused() {
        return this.elem === document.activeElement;
      }

      /**
       * Indicates that the element is not hidden or disabled
       */
      get active() {
        return !this.hidden && !this.disabled;
      }

      /**
       * Initialize directive instance.
       *
       * Called after instance created and attached to an element
       *
       * Typical behaviour:
       * - inspect element attributes
       * - initialize properties/parameters/value
       * - set up event handlers
       */
      init() {}

      /**
       * Render content of the directive
       *
       * May be called from `init` and `update`.
       *
       * Typical behaviour:
       * - `this.elem.innerHMTL = ...`
       *
       * For partial redraw, use `render()` for initial rendering, and define `renderSomething()` to redraw fragments
       */
      render() {}

      /**
       * Handle update of properties.
       *
       * Typically called from default 'onUpdate` handler,
       * triggered by `update` event.
       *
       * Base behaviour: call `render()` to redraw content.
       *
       * For partial redraw use something like:
       * `if (updated.has('foo')) this.redrawFoo()`
       *
       * @param {Set} updated set of updated properties (use `updated.has('something')` to check)
       */
      update(updated) {
        this.render();
      }

      /**
       * Handle update of value.
       *
       * Typically called from default 'onChange` handler,
       * trigered by intrinsic interaction, or `resetInputs`, or `ot-value`.
       *
       * Base behaviour: call `render()` to redraw content
       */
      reset() {
        this.render();
      }

      /**
       * Trigger `input` event.
       *
       * Generates the event using `this.name` and `this.value`
       *
       * Called from handler of internal change, or forced by `commitInput`
       *
       * @param {any} value another value to override `this.value`
       */
      commit(value) {
        if (value === undefined) value = this.value;
        this.triggerPageEvent('ot.input', {
          name: this.name,
          value
        });
      }

      /**
       * Initialize properties from attributes according to class-level `params`
       *
       * Properties with missing attributes are initialized by configured default values, or left undefined.
       *
       * Attriutes containing `vars.something` create references to track the variables and update later.
       * Initial value is either configured default or undefined.
       *
       * *CAUTION*: this also resets element.value
       */
      initParams() {
        this.paramVars = {};
        for (let param in this.params) {
          let conf = this.params[param];
          let value = this.elem.getAttribute(conf.attr || param);
          if (typeof value == 'string' && value.startsWith("vars.")) {
            this.paramVars[param] = value.slice(5);
            value = undefined;
          }
          this[param] = isVoid(value) ? conf.default : value;
        }
      }

      /**
       * Update properties that reference to page variables.
       *
       * @param {Changes} changes from an `update` event (the `event.detail.changes`)
       * @return {Set} set of affected properties
       */
      updateParams(changes) {
        let affected = Object.entries(this.paramVars).filter(_ref => {
          let [p, v] = _ref;
          return changes.affect(v);
        });
        affected.forEach(_ref2 => {
          let [p, v] = _ref2;
          return this[p] = changes.extract(v);
        });
        return new Set(affected.map(_ref3 => {
          let [p, v] = _ref3;
          return p;
        }));
      }

      /**
       * Install event handler for an arbitrary element.
       *
       * The handler is called with `this` context.
       *
       * @param {HTMLElement} target an element to attach
       * @param {string} type event type (including `ot.` prefix if needed)
       * @param {eventHandler} handler a function to run, may reference class method as `this.onSomething`
       */
      onEvent(target, type, handler) {
        target.addEventListener(type, event => {
          try {
            handler.call(this, event);
          } catch (e) {
            console.error(e);
            console.error("Failed to handle '".concat(event.type, "' for ").concat(this.constructor.name, " at"), this.elem);
          }
        });
      }

      /**
       * Install a handler for page events.
       *
       * @param {string} type type of event  (including `ot.` prefix if needed)
       * @param {eventHandler} handler a function or a method
       */
      onPageEvent(type, handler) {
        this.onEvent(document.body, type, handler);
      }

      /**
       * Install a handler for local native events.
       *
       * @param {string} type type of a native event
       * @param {eventHandler} handler a function or a method
       */
      onElemEvent(type, handler) {
        this.onEvent(this.elem, type, handler);
      }

      /**
       * Trigger an bare event on the host element.
       *
       * @param {string} type type of an event
       */
      triggerElemEvent(type) {
        let event = new Event(type);
        this.elem.dispatchEvent(event);
      }

      /**
       * Trigger a page event.
       *
       * The generated event has additional property `event.source` pointing to the host element.
       *
       * @param {string} type type of a page event (including `ot.` prefix if needed)
       */
      triggerPageEvent(type, detail) {
        let event = new CustomEvent(type, {
          detail
        });
        event.source = this.elem;
        document.body.dispatchEvent(event);
      }
    }

    /**
     * Mapping of directive properties to html attributes.
     *
     * @typedef {Object.<string, ParamConf>} ParamsConfig
     */

    /**
     * Mapping of a property to html attribute
     * @typedef {object} ParamConf
     * @property {string} attr name of attribute, by default - the same as property
     * @property {any} default default value used when attribute is missing or refers to a variable
     */

    /**
     * Base class for dynamic content directives.
     *
     * Implements handling dynamic content via tracking of variables referenced in attributes.
     *
     * - calls `render()` from init
     * - calls `update()` when some vars change
     */
    class ContentDirective extends DirectiveBase {
      init() {
        this.initParams();
        this.render();
        this.onPageEvent('ot.update', this.onUpdate);
      }
      onUpdate(event) {
        let changes = event.detail.changes;
        let updated = this.updateParams(changes);
        if (updated.size) this.update(updated);
      }
    }

    /**
     * Base class for native-inputs directives.
     *
     * Implements handling of intrinsic changes of field value.
     *
     * Also, it implements handlig of `resetPage`, `resetInputs` and `commitInput`.
     *
     * - calls `update()` when value changes or resets.
     * - calls `commit()` when value changes or fored to commit.
     *
     * @property {string|any} value current value of the input
     */
    class NativeInput extends DirectiveBase {
      get value() {
        return this.elem.value;
      }
      set value(val) {
        this.elem.value = val;
      }
      init() {
        if (!isElemField(this.elem)) throw Error("This directive is for native inputs only");
        if (!this.elem.hasAttribute('name')) throw Error("Missing `name` attribute");
        this.name = this.elem.getAttribute('name');
        this.elem.setAttribute("input", "");
        this.initParams();
        this.render();
        this.onElemEvent('change', this.onChange);
        this.onElemEvent('ot.commit', this.onCommit);
        this.onElemEvent('ot.reset', this.onReset);
      }
      onChange() {
        if (!this.active) return; // might happen because of disabling -> defocusing -> change
        this.reset();
        this.commit();
      }
      onCommit() {
        this.commit();
      }
      onReset() {
        this.reset();
      }
    }

    /**
     * Base class for trigger-like directives.
     * Used by `ot-click-input` and `ot-key-input`
     *
     * Implements generating input event when some other event happens.
     * Can be used on bare elements with `name` and `value` attributes,
     * or combined with another input directive or widget.
     *
     * Also, it respects `ot-value`
     *
     * @property {boolean} isInput indicates that the element is input or another input directive attached
     */
    class TriggerInput extends DirectiveBase {
      init() {
        // check if there's another directive that can do comit
        this.combined = Array.from(Object.values(this.elem.ot)).find(i => i instanceof NativeInput || i instanceof WidgetDirective) !== undefined;
        if (!this.combined) {
          this.name = this.elem.getAttribute('name');
          this.elem.value = this.elem.getAttribute('value');
          this.elem.defaultValue = this.elem.value;
        }
        this.initParams();
      }

      /**
       * Generate input event.
       *
       * When combined with other directives, it delegates committing to them.
       */
      trigger() {
        if (!this.active) return;
        if (this.combined) {
          this.triggerElemEvent('ot.commit');
        } else {
          this.commit(this.elem.value);
        }
      }
    }

    /**
     * Main base class for widget-like custom directives
     *
     * Implements both updating dynamic content and generating input events.
     *
     * - calls `render()` from init
     * - calls `update()` when some vars change or the value being reset
     * - calls `commit()` when value changed or forced to commit
     *
     * @property {HTMLElemet} input linked input element, or the same host element
     * @property {string|any} value current value of the input
     */
    class WidgetDirective extends DirectiveBase {
      get value() {
        return this.input ? this.input.value : this.elem.value;
      }
      set value(val) {
        if (this.input) this.input.value = val;else this.elem.value = val;
      }
      init() {
        if (isElemField(this.elem)) throw Error("This directive is not for native inputs");
        if (!this.elem.hasAttribute('name') && !this.elem.hasAttribute('input')) throw Error("Missing `name` or `input` attribute");
        if (!this.params.value) this.params.value = {};
        if (this.elem.hasAttribute('input')) {
          this.name = this.elem.getAttribute('input');
          this.input = document.querySelector("input[name=".concat(this.name, "]"));
          if (!this.input) throw Error("Linked input not found: ".concat(this.name));
          if (this.input.hasAttribute("value")) {
            this.params.value.default = this.input.defaultValue;
          }
        } else {
          this.name = this.elem.getAttribute('name');
        }
        this.initParams(); // NB: initParams sets this.value from elem.attr or params.default
        if (this.input) this.input.defaultValue = this.value;else this.elem.defaultValue = this.value;
        this.render();
        this.onPageEvent('ot.update', this.onUpdate);
        this.onElemEvent('ot.commit', this.onCommit);
        if (this.input) {
          this.onEvent(this.input, "change", this.onChange);
          this.onEvent(this.input, "ot.reset", this.onReset);
        } else {
          this.onEvent(this.elem, "ot.reset", this.onReset);
        }
      }
      onUpdate(event) {
        let changes = event.detail.changes;
        let updated = this.updateParams(changes);
        if (updated.size) this.update(updated);
      }
      onChange() {
        if (!this.active) return;
        this.reset();
        this.commit();
      }
      onCommit() {
        this.commit();
      }
      onReset() {
        this.reset();
      }
    }

    /**
     * Create and attach directives to selected html elements.
     *
     * Instances of directives are created for each matching element.
     *
     * The instances are saved on the elements in `element.ot[classname]` properties.
     *
     * @param {Class} cls JavaScript class to use for directive
     * @param {string} selector CSS selector to select elements on page to attach
     */
    function attachDirective(cls, selector) {
      assertArgs("attachDirective", arguments, ['class', 'string']);
      document.querySelectorAll(selector).forEach(elem => {
        if (elem.ot === undefined) elem.ot = {};
        try {
          let inst = new cls(elem);
          inst.init();
          elem.ot[cls.name] = inst;
        } catch (e) {
          console.error(e);
          console.error("Failed to create directive ".concat(cls.name, " at"), elem);
        }
      });
    }

    /**
     * Inserts text content.
     *
     * The value may not contain any tags. All markup is converted to plain text.
     *
     * @example
     * <p ot-text="vars.contentvar"></p>
     *
     * @memberof directives
     * @alias [ot-text]
     * @hideconstructor
     */
    class otText extends ContentDirective {
      constructor() {
        super(...arguments);
        _defineProperty(this, "params", {
          val: {
            attr: 'ot-text'
          }
        });
      }
      render() {
        if (isVoid(this.val)) {
          this.elem.textContent = "";
        } else {
          this.elem.textContent = this.val;
        }
      }
    }

    /**
     * Inserts html content.
     *
     * The value may contain html tags. They are converted to corresponding html elements.
     *
     * @example
     * <p ot-html="vars.contentvar"></p>
     *
     * @memberof directives
     * @alias [ot-html]
     * @hideconstructor
     */

    class otHTML extends ContentDirective {
      constructor() {
        super(...arguments);
        _defineProperty(this, "params", {
          val: {
            attr: 'ot-html'
          }
        });
      }
      render() {
        if (isVoid(this.val)) {
          this.elem.innerHTML = "";
        } else {
          this.elem.innerHTML = this.val;
        }
      }
    }

    class otAttrBase extends ContentDirective {
      constructor() {
        super(...arguments);
        _defineProperty(this, "attr", "foo");
        _defineProperty(this, "params", {
          val: {
            attr: "ot-foo"
          }
        });
      }
      render() {
        if (isVoid(this.val)) {
          this.elem.removeAttribute(this.attr);
        } else {
          this.elem.setAttribute(this.attr, this.val);
        }
      }
    }

    /**
     * Sets attriute `min`.
     *
     * @example
     * <input type="range" name="foo" ot-min="vars.range.min" ot-max="vars.range.max" ot-step="vars.range.step">
     *
     * @memberof directives
     * @alias [ot-min]
     * @hideconstructor
     */
    class otMin extends otAttrBase {
      constructor() {
        super(...arguments);
        _defineProperty(this, "attr", "min");
        _defineProperty(this, "params", {
          val: {
            attr: "ot-min"
          }
        });
      }
    }

    /**
     * Sets attriute `max`.
     *
     * @example
     * <input type="range" name="foo" ot-min="vars.range.min" ot-max="vars.range.max" ot-step="vars.range.step">
     *
     * @memberof directives
     * @alias [ot-max]
     * @hideconstructor
     */
    class otMax extends otAttrBase {
      constructor() {
        super(...arguments);
        _defineProperty(this, "attr", "max");
        _defineProperty(this, "params", {
          val: {
            attr: "ot-max"
          }
        });
      }
    }

    /**
     * Sets attriute `step`.
     *
     * @example
     * <input type="range" name="foo" ot-min="vars.range.min" ot-max="vars.range.max" ot-step="vars.range.step">
     *
     * @memberof directives
     * @alias [ot-step]
     * @hideconstructor
     */
    class otStep extends otAttrBase {
      constructor() {
        super(...arguments);
        _defineProperty(this, "attr", "step");
        _defineProperty(this, "params", {
          val: {
            attr: "ot-step"
          }
        });
      }
    }

    /**
     * Sets attriute `width`.
     *
     * @example
     * <img ot-width="vars.image_width" ot-height="vars.image_height" ot-src="vars.image_url">
     *
     * @memberof directives
     * @alias [ot-width]
     * @hideconstructor
     */
    class otWidth extends otAttrBase {
      constructor() {
        super(...arguments);
        _defineProperty(this, "attr", "width");
        _defineProperty(this, "params", {
          val: {
            attr: "ot-width"
          }
        });
      }
    }

    /**
     * Sets attriute `height`.
     *
     * @example
     * <img ot-width="vars.image_width" ot-height="vars.image_height" ot-src="vars.image_url">
     *
     * @memberof directives
     * @alias [ot-height]
     * @hideconstructor
     */
    class otHeight extends otAttrBase {
      constructor() {
        super(...arguments);
        _defineProperty(this, "attr", "height");
        _defineProperty(this, "params", {
          val: {
            attr: "ot-height"
          }
        });
      }
    }

    /**
     * Sets attriute `href`.
     *
     * @example
     * <a ot-href="vars.link.url" ot-text="vars.link.text"></a>
     *
     * @memberof directives
     * @alias [ot-href]
     * @hideconstructor
     */
    class otHref extends otAttrBase {
      constructor() {
        super(...arguments);
        _defineProperty(this, "attr", "href");
        _defineProperty(this, "params", {
          val: {
            attr: "ot-href"
          }
        });
      }
    }

    /**
     * Sets attriute `src`.
     *
     * **NOTE**: Loading of an image takes some time due to network latency, so an image won't appear immediately after setting this attribute.
     * Use preloading utils to reduce the latency.
     *
     * @see preloadImage
     * @see preloadImages
     *
     * @example
     * <img ot-width="vars.image_width" ot-height="vars.image_height" ot-src="vars.image_url">
     *
     * @memberof directives
     * @alias [ot-src]
     * @hideconstructor
     */
    class otSrc extends otAttrBase {
      constructor() {
        super(...arguments);
        _defineProperty(this, "attr", "src");
        _defineProperty(this, "params", {
          val: {
            attr: "ot-src"
          }
        });
      }
    }

    /**
     * Adds css classes to an element.
     *
     * A referenced variable may contain a string, or a list of names.
     *
     * When it's value is set to null, classes are restored to initial list (from original `class` attribute)
     *
     * @example
     * <div class="foo" ot-class="vars.foo_class">...</div>
     *
     * @memberof directives
     * @alias [ot-class]
     * @hideconstructor
     */
    class otClass extends ContentDirective {
      constructor() {
        super(...arguments);
        _defineProperty(this, "params", {
          val: {
            attr: 'ot-class'
          }
        });
      }
      init() {
        this.initial = Array.from(this.elem.classList);
        super.init();
      }
      render() {
        let classList = this.initial.slice();
        if (!isVoid(this.val)) {
          if (Array.isArray(this.val)) {
            classList = classList.concat(this.val);
          } else {
            classList.push(this.val);
          }
        }
        this.elem.classList.remove(...this.elem.classList);
        this.elem.classList.add(...classList);
      }
    }

    /**
     * Sets an input/widget value.
     *
     * The value is set as if it was provided via `value` attribute, or reset with `resetInput(name, value)`
     *
     * Text inputs would put the value in their fields.
     * Non standard widgets are notified about the change via `reset` event, in hope that they would change their appearence appropriately.
     *
     * @see resetInput
     *
     * @example
     * <input type="text" name="answer" ot-value="vars.answer">
     * <input type="radio" name="choice" ot-value="vars.choices.1">
     * <input type="radio" name="choice" ot-value="vars.choices.2">
     * <some-widget ot-value="vars.foo">...</some-widget>
     *
     * @memberof directives
     * @alias [ot-value]
     * @hideconstructor
     */
    class otValue extends ContentDirective {
      constructor() {
        super(...arguments);
        _defineProperty(this, "params", {
          val: {
            attr: "ot-value"
          }
        });
      }
      update() {
        if (isVoid(this.val)) {
          this.elem.value = null;
        } else {
          this.elem.value = this.val;
        }
        this.triggerElemEvent('ot.reset');
      }
    }

    /**
     * Handles native input fields.
     *
     * Generates input event whenever field value changes by some interaction.
     *
     * @example
     * <select ot-input name="choice">
     *   <option value="1">One</option>
     *   <option value="2">Two</option>
     * </select>
     *
     * @memberof directives
     * @alias [ot-input]
     * @emits directives.input
     * @hideconstructor
     */
    class otInput extends NativeInput {}

    /**
     * Handles text input fields.
     *
     * The input event is generated only when the field is defocused (this is their default input behviour).
     * To make it commit automatically after pause (350ms by default), add `autocommit` attribute.
     * To make it commit value on 'Enter', combine it with `ot-key-input`.
     *
     * If `type=number` the reported value is converted to a number, otherwise it's string.
     *
     * @see [ot-key-input]
     *
     * @example
     * <input type="text" ot-input name="answer" autocommit>
     * <input type="text" ot-input name="answer" autocommit="100">
     * <input type="number" ot-input name="answer" ot-key-input="Enter">
     *
     * @memberof directives
     * @alias [ot-input][type=text]
     * @emits directives.input
     * @hideconstructor
     */
    class otTextInput extends NativeInput {
      constructor() {
        super(...arguments);
        _defineProperty(this, "params", {
          // hack: set it to 1ms which also evaluates true for the if-statement below.
          autocommit: {
            default: 1
          }
        });
      }
      init() {
        super.init();
        this.onElemEvent('keypress', this.onKey);
        if (this.autocommit == "") this.autocommit = 350;
        if (this.autocommit) {
          this.onElemEvent('input', this.onAutocommit);
        }
        this.onElemEvent('change', this.onChange);
        this.onElemEvent('change', function () {
          this.triggerPageEvent('ot.commit_input', {
            name: this.name,
            value: this.value
          });
        });
      }
      commit() {
        if (this.elem.type == "number") super.commit(Number(this.value));else super.commit();
      }
      onKey(e) {
        // NB: preventing auto submitting of form
        if (e.key === 'Enter') e.preventDefault();
      }
      onAutocommit() {
        if (this.commit_timeout) window.clearTimeout(this.commit_timeout);
        this.commit_timeout = window.setTimeout(() => this.commit(), this.autocommit);
      }
    }

    /**
     * Handles slider input field.
     *
     * It's reported value is converted to number
     *
     * @example
     * <input type="range" ot-input name="foo" min="1" max="10" step="1">
     *
     * @memberof directives
     * @alias [ot-input][type=range]
     * @emits directives.input
     * @hideconstructor
     */
    class otRangeInput extends NativeInput {
      commit() {
        super.commit(Number(this.value));
      }
    }

    /**
     * Handles radio input field.
     *
     * It reports only the value of selected/checked radio button
     *
     * @example
     * <input type="radio" ot-input name="choice" value="A">
     * <input type="radio" ot-input name="choice" value="B">
     *
     * @memberof directives
     * @alias [ot-input][type=radio]
     * @emits directives.input
     * @hideconstructor
     */
    class otRadioInput extends NativeInput {
      commit() {
        if (this.elem.checked) super.commit();
      }
    }

    /**
     * Handles checkbox field.
     *
     * It reports `true`/`false` values by default.
     * If there's `value` attribute, it is reported when the box is checked, and `null` reported when unchecked.
     *
     * @example
     * <input type="checkbox" ot-input name="foo">
     * <input type="checkbox" ot-input name="bar" value="Bar">
     *
     * @memberof directives
     * @alias [ot-input][type=checkbox]
     * @emits directives.input
     * @hideconstructor
     */
    class otCheckInput extends NativeInput {
      commit() {
        if (this.elem.value == "on") {
          super.commit(this.elem.checked);
        } else {
          super.commit(this.elem.checked ? this.value : null);
        }
      }
    }

    /**
     * Reports clicks.
     *
     * Generates an input event when host element is clicked.
     *
     * @example
     * <button type="button" ot-click-input name="choice" value="foo">Foo</button>
     *
     * @memberof directives
     * @alias [ot-click-input]
     * @emits directives.input
     * @hideconstructor
     */
    class otClick extends TriggerInput {
      init() {
        super.init();
        this.onElemEvent('click', this.onClick);
      }
      onClick() {
        if (!this.active) return;
        this.trigger();
      }
    }

    /**
     * Reports keypress.
     *
     * Generates an input event when specified key is pressed.
     * The input works globally, its host element doesn't need to be active/focused.
     *
     * Key can be specified by either letter or a keycode from
     * [this table](https://developer.mozilla.org/en-US/docs/Web/API/UI_Events/Keyboard_event_code_values)
     *
     * If you specify a letter such as `ot-key-input="z"`, that depends on user's keyboard layout to produce such letter.
     * If you specify a keycode such as `ot-key-input="KeyZ", that refers to a particular physical key no matter the layout.
     *
     * @example
     * <kbd ot-key-input="ArrowLeft" name="direction" value="left">left</kbd>
     * <kbd ot-key-input="ArrowRight" name="direction" value="right">right</kbd>
     *
     * @memberof directives
     * @alias [ot-key-input]
     * @emits directives.input
     * @hideconstructor
     */
    class otKey extends TriggerInput {
      constructor() {
        super(...arguments);
        _defineProperty(this, "params", {
          key: {
            attr: 'ot-key-input'
          }
        });
      }
      init() {
        super.init();
        if (this.key.length != 1 && !this.key.match(/[A-Z]\w+/)) {
          throw new Error("Invalid key name: \"".concat(this.key, "\", expected a letter or a codename."));
        }
        if (isElemEditable(this.elem)) {
          this.onElemEvent("keypress", this.onKey);
        } else {
          this.onPageEvent("keypress", this.onKey);
        }
      }
      onKey(event) {
        if (!this.active || this.key != event.key && this.key != event.code) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        this.trigger();
      }
    }

    /**
     * Reports clicks with coordinates.
     *
     * Generates event when host element is clicked.
     * Reported value is an object `{x, y}` with coordinates of the click.
     *
     * @example
     * <img src="..." width="500" height="500" ot-point-input name="click">
     *
     * @memberof directives
     * @alias [ot-point-input]
     * @emits directives.input
     * @hideconstructor
     */

    class otPoint extends DirectiveBase {
      init() {
        super.init();
        this.name = this.elem.getAttribute('name');
        this.onElemEvent('click', this.onClick);
      }
      onClick(event) {
        if (!this.active) return;
        this.commit({
          x: event.offsetX,
          y: event.offsetY
        });
      }
    }

    function attachDirectives() {
      // content directives
      attachDirective(otText, "[ot-text]");
      attachDirective(otHTML, "[ot-html]");
      attachDirective(otMin, "[ot-min]");
      attachDirective(otMax, "[ot-max]");
      attachDirective(otStep, "[ot-step]");
      attachDirective(otWidth, "[ot-width]");
      attachDirective(otHeight, "[ot-height]");
      attachDirective(otSrc, "[ot-src]");
      attachDirective(otHref, "[ot-href]");
      attachDirective(otClass, "[ot-class]");
      attachDirective(otValue, "[ot-value]");
      // native inputs
      attachDirective(otTextInput, "input:is([type=text],[type=number])");
      attachDirective(otTextInput, "textarea");
      attachDirective(otRangeInput, "input[type=range]");
      attachDirective(otRadioInput, "input[type=radio]");
      attachDirective(otCheckInput, "input[type=checkbox]");
      attachDirective(otInput, "input:not([type=text],[type=number],[type=range],[type=radio],[type=checkbox],[type=button])");
      attachDirective(otInput, "select");
      //
      attachDirective(otPoint, "[ot-point-input]");
      // triggers, should go last to detect combos
      attachDirective(otKey, "[ot-key-input]");
      attachDirective(otClick, "button");
      attachDirective(otClick, "input[type=button]");
    }

    /**
     * Default initialization function.
     * Called when page is loaded, before other scripts are executed.
     * Can be overriden by defining alternative global `initApp` function
     */
    function initApp() {
      attachDirectives();
      initPage();
      initVars();
      initTimers();
    }

    /**
     * Default startup function.
     * Called when page is fully loaded and all scripts executed.
     * Can be overriden by defining alternative global `startApp` function
     */
    function startApp() {
      startPage();
    }
    window.addEventListener("DOMContentLoaded", window.initApp || initApp);
    window.addEventListener("load", window.startApp || startApp);

    exports.ContentDirective = ContentDirective;
    exports.DirectiveBase = DirectiveBase;
    exports.NativeInput = NativeInput;
    exports.TriggerInput = TriggerInput;
    exports.WidgetDirective = WidgetDirective;
    exports.attachDirective = attachDirective;
    exports.beginTimeMeasurement = beginTimeMeasurement;
    exports.cancelTimer = cancelTimer;
    exports.cancelTimers = cancelTimers;
    exports.commitInput = commitInput;
    exports.completePage = completePage;
    exports.delay = delay;
    exports.delayEvent = delayEvent;
    exports.disableElem = disableElem;
    exports.disableInput = disableInput;
    exports.disableInputs = disableInputs;
    exports.emitEvent = emitEvent;
    exports.enableElem = enableElem;
    exports.enableInput = enableInput;
    exports.enableInputs = enableInputs;
    exports.getTimeMeasurement = getTimeMeasurement;
    exports.hideDisplay = hideDisplay;
    exports.hideDisplays = hideDisplays;
    exports.hideElem = hideElem;
    exports.initApp = initApp;
    exports.initPage = initPage;
    exports.initTimers = initTimers;
    exports.initVars = initVars;
    exports.isArray = isArray;
    exports.isElemCheckable = isElemCheckable;
    exports.isElemEditable = isElemEditable;
    exports.isElemField = isElemField;
    exports.isElemNavigable = isElemNavigable;
    exports.isFunction = isFunction;
    exports.isObject = isObject;
    exports.isPlainObject = isPlainObject;
    exports.isScalar = isScalar;
    exports.isVoid = isVoid;
    exports.onEvent = onEvent;
    exports.otCheckInput = otCheckInput;
    exports.otClass = otClass;
    exports.otClick = otClick;
    exports.otHTML = otHTML;
    exports.otHeight = otHeight;
    exports.otHref = otHref;
    exports.otInput = otInput;
    exports.otKey = otKey;
    exports.otMax = otMax;
    exports.otMin = otMin;
    exports.otPoint = otPoint;
    exports.otRadioInput = otRadioInput;
    exports.otRangeInput = otRangeInput;
    exports.otSrc = otSrc;
    exports.otStep = otStep;
    exports.otText = otText;
    exports.otTextInput = otTextInput;
    exports.otValue = otValue;
    exports.otWidth = otWidth;
    exports.preloadImage = preloadImage;
    exports.preloadImages = preloadImages;
    exports.resetInput = resetInput;
    exports.resetInputs = resetInputs;
    exports.showDisplay = showDisplay;
    exports.showDisplays = showDisplays;
    exports.showElem = showElem;
    exports.startApp = startApp;
    exports.startPage = startPage;
    exports.startTimer = startTimer;
    exports.startTimerPeriodic = startTimerPeriodic;
    exports.startTimerSequence = startTimerSequence;
    exports.submitPage = submitPage;
    exports.triggerEvent = triggerEvent;
    exports.updatePage = updatePage;

    return exports;

})({});

Object.freeze(otc);
