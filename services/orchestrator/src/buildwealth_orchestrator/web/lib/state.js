export const state = {
  conversations: [],
  currentConversationId: null,
  currentMessages: [],
  copilotLoading: false,
  plans: [],
  currentPlanId: null,
  currentPlanDetail: null,
  copilotPlanId: '',
  workflowTemplates: [],
  todayDashboard: null,
  financialProfile: null,
  onboardingStatus: null,
  recommendations: [],
  recommendationFilterStatus: 'proposed',
  recommendationFilterPlanId: '',
  recommendationEditingId: null,
};

export const PLAN_SETTING_FIELDS = [
  { key: 'annual_contribution_usd', inputId: 'setting-annual-contribution', label: 'Annual Contribution (USD)', scale: 1, integer: false, step: 100, min: 0, placeholder: 'e.g. 22000' },
  { key: 'years', inputId: 'setting-years', label: 'Horizon (Years)', scale: 1, integer: true, step: 1, min: 1, max: 80, placeholder: 'e.g. 25' },
  { key: 'hsa_extra_contribution_usd', inputId: 'setting-hsa-extra', label: 'HSA Extra (USD)', scale: 1, integer: false, step: 100, min: 0, placeholder: 'e.g. 1000' },
  { key: 'marginal_tax_rate', inputId: 'setting-marginal-tax-rate', label: 'Tax Rate (%)', scale: 100, integer: false, step: 0.01, min: 0, max: 100, placeholder: 'e.g. 24' },
  { key: 'inflation_rate', inputId: 'setting-inflation-rate', label: 'Inflation Rate (%)', scale: 100, integer: false, step: 0.01, min: -100, max: 100, placeholder: 'e.g. 3' },
  { key: 'expected_return_baseline', inputId: 'setting-return-baseline', label: 'Baseline Return (%)', scale: 100, integer: false, step: 0.01, min: -95, max: 100, placeholder: 'e.g. 7' },
  { key: 'expected_return_optimistic', inputId: 'setting-return-optimistic', label: 'Optimistic Return (%)', scale: 100, integer: false, step: 0.01, min: -95, max: 100, placeholder: 'e.g. 9' },
  { key: 'expected_return_conservative', inputId: 'setting-return-conservative', label: 'Conservative Return (%)', scale: 100, integer: false, step: 0.01, min: -95, max: 100, placeholder: 'e.g. 5' },
];

export const DIFF_SETTING_FIELDS = PLAN_SETTING_FIELDS.map(f => ({
  ...f,
  inputId: f.inputId.replace('setting-', 'diff-'),
  placeholder: 'Optional',
}));
