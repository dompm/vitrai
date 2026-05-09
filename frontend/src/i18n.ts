import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

const resources = {
  en: {
    translation: {
      result: "Result",
      pattern: "Pattern",
      load: "Load",
      save: "Save",
      reset: "Reset",
      invalidProject: "Invalid project file",
      saveTooltip: "Save project",
      resetTooltip: "Reset to defaults",
      uploadSheetTooltip: "Upload sheet",
      toolSelect: "Select",
      toolCropPattern: "Crop pattern",
      toolCropSheet: "Crop sheet",
      toolScalePattern: "Set pattern scale",
      toolScaleSheet: "Set sheet scale",
      toolDrawBox: "Add piece (draw box)",
      toolDetectAll: "Detect all pieces",
      toolInspect: "Inspect pattern",
      tooltipSelectName: "Select",
      tooltipSelectDescPattern: "Click pieces to select and inspect them",
      tooltipSelectDescSheet: "Click pieces to select and position them",
      tooltipCropPatternName: "Crop Pattern",
      tooltipCropPatternDesc: "Trim the pattern edges to the working area",
      tooltipCropSheetName: "Crop Sheet",
      tooltipCropSheetDesc: "Trim the glass sheet edges to the working area",
      tooltipScaleName: "Set Scale",
      tooltipScaleDescPattern: "Draw a line and enter its real-world size to calibrate scale",
      tooltipScaleDescSheet: "Set the real-world scale of the glass sheet",
      tooltipBoxName: "Draw Box",
      tooltipBoxDesc: "Draw a box around a piece to detect its shape",
      tooltipDetectAllName: "Detect All",
      tooltipDetectAllDesc: "Auto-detect all pieces in the pattern at once",
      tooltipInspectName: "Inspect Pattern",
      tooltipInspectDesc: "Hide glass pieces to see the original pattern clearly",
      clickToRename: "Click to rename",
      sheet: "Sheet",
      addSheetOption: "Add sheet…",
      addPositivePoint: "Add positive point (+)",
      addNegativePoint: "Add negative point (-)",
      deletePieceTooltip: "Delete piece (Del)",
      delete: "Delete",
      lengthPlaceholder: "length",
      piece: "Piece",
      pieces: "pieces",
      glass: "Glass",
      unit_mm: "mm",
      unit_cm: "cm",
      unit_in: "in"
    }
  },
  fr: {
    translation: {
      result: "Résultat",
      pattern: "Patron",
      load: "Charger",
      save: "Sauvegarder",
      reset: "Réinitialiser",
      invalidProject: "Fichier de projet invalide",
      saveTooltip: "Sauvegarder le projet",
      resetTooltip: "Réinitialiser",
      uploadSheetTooltip: "Téléverser une plaque",
      toolSelect: "Sélectionner",
      toolCropPattern: "Recadrer le patron",
      toolCropSheet: "Recadrer la plaque",
      toolScalePattern: "Échelle du patron",
      toolScaleSheet: "Échelle de la plaque",
      toolDrawBox: "Ajouter pièce (tracer boîte)",
      toolDetectAll: "Détecter tout",
      toolInspect: "Inspecter le patron",
      tooltipSelectName: "Sélectionner",
      tooltipSelectDescPattern: "Cliquez sur les pièces pour les inspecter",
      tooltipSelectDescSheet: "Cliquez sur les pièces pour les positionner",
      tooltipCropPatternName: "Recadrer Patron",
      tooltipCropPatternDesc: "Ajustez les bords du patron à la zone de travail",
      tooltipCropSheetName: "Recadrer Plaque",
      tooltipCropSheetDesc: "Ajustez les bords de la plaque de verre à la zone de travail",
      tooltipScaleName: "Échelle",
      tooltipScaleDescPattern: "Tracez une ligne et entrez sa taille réelle pour calibrer l'échelle",
      tooltipScaleDescSheet: "Définissez l'échelle réelle de la plaque de verre",
      tooltipBoxName: "Tracer Boîte",
      tooltipBoxDesc: "Tracez une boîte autour d'une pièce pour détecter sa forme",
      tooltipDetectAllName: "Détecter Tout",
      tooltipDetectAllDesc: "Détecter automatiquement toutes les pièces du patron",
      tooltipInspectName: "Inspecter le Patron",
      tooltipInspectDesc: "Cachez les pièces de verre pour voir le patron original clairement",
      clickToRename: "Cliquez pour renommer",
      sheet: "Plaque",
      addSheetOption: "Ajouter une plaque…",
      addPositivePoint: "Ajouter un point positif (+)",
      addNegativePoint: "Ajouter un point négatif (-)",
      deletePieceTooltip: "Supprimer la pièce (Suppr)",
      delete: "Supprimer",
      lengthPlaceholder: "longueur",
      piece: "Pièce",
      pieces: "pièces",
      glass: "Verre",
      unit_mm: "mm",
      unit_cm: "cm",
      unit_in: "po"
    }
  }
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false,
    }
  });

export default i18n;
