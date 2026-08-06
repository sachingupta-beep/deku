import { HABIT_COLORS, type HabitColor } from '../types';

interface ColorPickerProps {
  value: HabitColor;
  onChange: (color: HabitColor) => void;
}

const colorNames: HabitColor[] = ['indigo', 'teal', 'amber', 'rose', 'slate', 'forest'];

export function ColorPicker({ value, onChange }: ColorPickerProps) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-900">Color</label>
      <div className="flex gap-2">
        {colorNames.map((color) => (
          <button
            key={color}
            type="button"
            onClick={() => onChange(color)}
            className={`
              w-8 h-8 rounded-full transition-all duration-150
              focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary
              ${value === color ? 'ring-2 ring-offset-2 ring-gray-900 scale-110' : 'hover:scale-105'}
            `}
            style={{ backgroundColor: HABIT_COLORS[color] }}
            aria-label={`Select ${color} color`}
          />
        ))}
      </div>
    </div>
  );
}
