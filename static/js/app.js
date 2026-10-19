/* Drystone Cobble Street Survey — progressive enhancement only.
   Everything works without JavaScript; this file adds the two interactive
   affordances the forms need: a password reveal and a guarded submit state. */
(function () {
  "use strict";

  /* ---------------------------------------------------- password show / hide */

  var toggles = document.querySelectorAll("[data-password-toggle]");
  Array.prototype.forEach.call(toggles, function (button) {
    var input = document.getElementById(button.getAttribute("data-password-toggle"));
    if (!input) {
      return;
    }
    button.addEventListener("click", function () {
      var revealed = input.getAttribute("type") === "text";
      input.setAttribute("type", revealed ? "password" : "text");
      button.textContent = revealed ? "Show" : "Hide";
      button.setAttribute("aria-pressed", revealed ? "false" : "true");
      input.focus();
    });
  });

  /* --------------------------------------------------- inline field required */

  function errorSlot(field) {
    return document.querySelector('[data-error-for="' + field.id + '"]');
  }

  function setFieldError(field, message) {
    var slot = errorSlot(field);
    if (slot) {
      slot.textContent = message;
      slot.hidden = false;
    }
    field.setAttribute("aria-invalid", "true");
  }

  function clearFieldError(field) {
    var slot = errorSlot(field);
    if (slot) {
      slot.textContent = "";
      slot.hidden = true;
    }
    field.removeAttribute("aria-invalid");
  }

  function requiredFields(form) {
    return Array.prototype.slice.call(
      form.querySelectorAll("[data-required-label]")
    );
  }

  function validate(form) {
    var firstInvalid = null;
    requiredFields(form).forEach(function (field) {
      var message = field.getAttribute("data-required-label");
      if (field.value.trim() === "") {
        setFieldError(field, message);
        if (!firstInvalid) {
          firstInvalid = field;
        }
      } else {
        clearFieldError(field);
      }
    });
    if (firstInvalid) {
      firstInvalid.focus();
      return false;
    }
    return true;
  }

  Array.prototype.forEach.call(
    document.querySelectorAll("form[data-guard]"),
    function (form) {
      var pending = false;

      requiredFields(form).forEach(function (field) {
        field.addEventListener("input", function () {
          if (field.value.trim() !== "") {
            clearFieldError(field);
          }
        });
      });

      form.addEventListener("submit", function (event) {
        if (!validate(form)) {
          event.preventDefault();
          return;
        }
        if (pending) {
          event.preventDefault();
          return;
        }
        pending = true;
        var button = form.querySelector('button[type="submit"]');
        if (button) {
          button.disabled = true;
          button.setAttribute("aria-busy", "true");
          button.classList.add("is-busy");
          var busyLabel = button.getAttribute("data-busy-label");
          if (busyLabel) {
            button.setAttribute("data-idle-label", button.textContent);
            button.textContent = busyLabel;
          }
        }
      });
    }
  );

  /* -------------------------------------------------- destructive confirmation */

  Array.prototype.forEach.call(
    document.querySelectorAll("form[data-confirm]"),
    function (form) {
      form.addEventListener("submit", function (event) {
        var message = form.getAttribute("data-confirm");
        if (message && !window.confirm(message)) {
          event.preventDefault();
        }
      });
    }
  );
})();
