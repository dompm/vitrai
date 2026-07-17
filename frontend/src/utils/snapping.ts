export interface SnapFraction {
  value: number;
  label: string;
}

export function getSnapFractions(t: (key: string) => string): SnapFraction[] {
  const FRACTIONS: SnapFraction[] = [];
  const seen = new Set<string>();
  const denominators = [2, 3, 4, 5, 6, 8, 10, 12, 16];
  
  for (const d of denominators) {
    for (let n = 1; n < d; n++) {
      const gcd = (a: number, b: number): number => b === 0 ? a : gcd(b, a % b);
      const g = gcd(n, d);
      const num = n / g;
      const den = d / g;
      const key = `${num}/${den}`;
      if (!seen.has(key)) {
        seen.add(key);
        const val = num / den;
        const label = den === 2 ? t('snapCenter') : key;
        FRACTIONS.push({ value: val, label });
      }
    }
  }
  return FRACTIONS;
}
