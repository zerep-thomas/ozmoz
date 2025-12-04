/* --- static/js/settings/constants.js --- */

window.NOVA3_SUPPORTED_LANGUAGES = [
  "en",
  "es",
  "fr",
  "de",
  "hi",
  "ru",
  "pt",
  "ja",
  "it",
  "nl",
  "sv",
  "da",
];

window.LANGUAGES_DATA = [
  { value: "autodetect", key: "lang_autodetect", flag: "" },
  {
    value: "fr",
    key: "lang_fr",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1eb-1f1f7.svg">',
  },
  {
    value: "en",
    key: "lang_en",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1ec-1f1e7.svg">',
  },
  {
    value: "de",
    key: "lang_de",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1e9-1f1ea.svg">',
  },
  {
    value: "de-CH",
    key: "lang_de_ch",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1e8-1f1ed.svg">',
  },
  {
    value: "es",
    key: "lang_es",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1ea-1f1f8.svg">',
  },
  {
    value: "it",
    key: "lang_it",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1ee-1f1f9.svg">',
  },
  {
    value: "pt",
    key: "lang_pt",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f5-1f1f9.svg">',
  },
  {
    value: "ja",
    key: "lang_ja",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1ef-1f1f5.svg">',
  },
  {
    value: "ko",
    key: "lang_ko",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f0-1f1f7.svg">',
  },
  {
    value: "zh",
    key: "lang_zh",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1e8-1f1f3.svg">',
  },
  {
    value: "zh-HK",
    key: "lang_zh_hk",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1ed-1f1f0.svg">',
  },
  {
    value: "zh-TW",
    key: "lang_zh_tw",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f9-1f1fc.svg">',
  },
  {
    value: "ru",
    key: "lang_ru",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f7-1f1fa.svg">',
  },
  {
    value: "nl",
    key: "lang_nl",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f3-1f1f1.svg">',
  },
  {
    value: "nl-BE",
    key: "lang_nl_be",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1e7-1f1ea.svg">',
  },
  {
    value: "pl",
    key: "lang_pl",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f5-1f1f1.svg">',
  },
  {
    value: "tr",
    key: "lang_tr",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f9-1f1f7.svg">',
  },
  {
    value: "hi",
    key: "lang_hi",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1ee-1f1f3.svg">',
  },
  {
    value: "sv",
    key: "lang_sv",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f8-1f1ea.svg">',
  },
  {
    value: "da",
    key: "lang_da",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1e9-1f1f0.svg">',
  },
  {
    value: "fi",
    key: "lang_fi",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1eb-1f1ee.svg">',
  },
  {
    value: "no",
    key: "lang_no",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f3-1f1f4.svg">',
  },
  {
    value: "bg",
    key: "lang_bg",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1e7-1f1ec.svg">',
  },
  {
    value: "et",
    key: "lang_et",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1ea-1f1ea.svg">',
  },
  {
    value: "el",
    key: "lang_el",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1ec-1f1f7.svg">',
  },
  {
    value: "hu",
    key: "lang_hu",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1ed-1f1fa.svg">',
  },
  {
    value: "id",
    key: "lang_id",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1ee-1f1e9.svg">',
  },
  {
    value: "lv",
    key: "lang_lv",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f1-1f1fb.svg">',
  },
  {
    value: "lt",
    key: "lang_lt",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f1-1f1f9.svg">',
  },
  {
    value: "ms",
    key: "lang_ms",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f2-1f1fe.svg">',
  },
  {
    value: "ro",
    key: "lang_ro",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f7-1f1f4.svg">',
  },
  {
    value: "sk",
    key: "lang_sk",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f8-1f1f0.svg">',
  },
  {
    value: "cs",
    key: "lang_cs",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1e8-1f1ff.svg">',
  },
  {
    value: "th",
    key: "lang_th",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1f9-1f1ed.svg">',
  },
  {
    value: "uk",
    key: "lang_uk",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1fa-1f1e6.svg">',
  },
  {
    value: "vi",
    key: "lang_vi",
    flag: '<img class="lang-flag" src="https://images.emojiterra.com/google/noto-emoji/unicode-16.0/color/svg/1f1fb-1f1f3.svg">',
  },
];
