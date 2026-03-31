/**
 * app.js — Calculadora de Deliveries
 * Utilidades globales de UI
 */

// Bloquear doble-submit en formularios
document.addEventListener("DOMContentLoaded", () => {
  const forms = document.querySelectorAll("form:not([data-no-block])");
  forms.forEach((form) => {
    form.addEventListener("submit", () => {
      const submitBtn = form.querySelector('[type="submit"]');
      if (submitBtn) {
        submitBtn.classList.add("btn-loading");
        submitBtn.innerHTML =
          '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Calculando...';
      }
    });
  });

  // Auto-dismiss flash messages después de 6s
  const alerts = document.querySelectorAll(".alert.alert-dismissible");
  alerts.forEach((alert) => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    }, 6000);
  });
});
