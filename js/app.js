/**
 * FoodShield AI - Main Application Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  // Initialize UI bindings & state
  UI.init();

  const riskForm = document.getElementById('riskForm');

  if (riskForm) {
    riskForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      // Get structured form inputs
      const formData = UI.getFormData();

      // Show loading UI state
      UI.showLoading();

      try {
        // Execute real request to Google Gemini API
        const resultData = await analyzeFoodSecurityRisk(formData);
        
        // Render JSON analysis results
        UI.renderResults(resultData);
      } catch (err) {
        console.error("Analysis Error:", err);
        UI.showError(err.message || "AI analysis failed. Please verify API key and network connection.");
      }
    });
  }
});
