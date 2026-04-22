import {
  CalendarDays,
  CloudRain,
  CloudSun,
  Droplets,
  Gauge,
  History,
  Sunrise,
  Sunset,
  Thermometer,
  Wind
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

const COPY = {
  ru: {
    titles: {
      current: "Сейчас",
      forecastDay: "День",
      forecastWeek: "Неделя",
      forecastDense: "Диапазон",
      forecastMonth: "Обзор",
      history: "История"
    },
    fallbackTitle: "Погода",
    noDescription: "Без описания",
    currentFallback: "Текущая погода",
    historyFallback: "Историческая дата",
    feels: "Ощущается",
    humidity: "Влажн.",
    wind: "Ветер",
    pressure: "Давл.",
    avg: "Средняя",
    rain: "Дождь",
    morning: "Утро",
    day: "День",
    evening: "Вечер",
    min: "Мин",
    max: "Макс",
    precip: "Осадки",
    updatedPrefix: "Обновлено",
    sunrise: "Восход",
    sunset: "Закат",
    forecastAction: "Ещё 3 дня",
    umbrellaAction: "Зонт?",
    compareAction: "Сравнить день",
    walkAction: "Когда гулять?",
    compareHistoryAction: "Сравнить с текущей",
    forecastPrompt: (city) => `Покажи прогноз на 3 дня для ${city || "Краснодара"}`,
    umbrellaPrompt: (city) => `Нужен ли зонт в ${city || "Краснодаре"}?`,
    comparePrompt: (city) => `Сравни утро, день и вечер по прогнозу в ${city || "Краснодаре"}`,
    walkPrompt: (city) => `Когда лучше выйти на прогулку в ${city || "Краснодаре"}?`,
    compareHistoryPrompt: (city) =>
      `Сравни эту историческую погоду с текущей в ${city || "Краснодаре"}`,
    windUnit: " км/ч",
    pressureUnit: " мбар",
    precipUnit: " мм",
    dayFallback: (index) => `День ${index + 1}`,
    fallbackCity: "Краснодар"
  },
  en: {
    titles: {
      current: "Now",
      forecastDay: "Day",
      forecastWeek: "Week",
      forecastDense: "Range",
      forecastMonth: "Overview",
      history: "History"
    },
    fallbackTitle: "Weather",
    noDescription: "No description",
    currentFallback: "Current weather",
    historyFallback: "Historical date",
    feels: "Feels like",
    humidity: "Humidity",
    wind: "Wind",
    pressure: "Pressure",
    avg: "Average",
    rain: "Rain",
    morning: "Morning",
    day: "Day",
    evening: "Evening",
    min: "Min",
    max: "Max",
    precip: "Precip",
    updatedPrefix: "Updated",
    sunrise: "Sunrise",
    sunset: "Sunset",
    forecastAction: "More 3 days",
    umbrellaAction: "Umbrella?",
    compareAction: "Compare day",
    walkAction: "Best walk time?",
    compareHistoryAction: "Compare with current",
    forecastPrompt: (city) => `Show a 3-day forecast for ${city || "Krasnodar"}`,
    umbrellaPrompt: (city) => `Do I need an umbrella in ${city || "Krasnodar"}?`,
    comparePrompt: (city) =>
      `Compare the morning, day, and evening forecast in ${city || "Krasnodar"}`,
    walkPrompt: (city) => `When is the best time for a walk in ${city || "Krasnodar"}?`,
    compareHistoryPrompt: (city) =>
      `Compare this historical weather with the current weather in ${city || "Krasnodar"}`,
    windUnit: " km/h",
    pressureUnit: " mb",
    precipUnit: " mm",
    dayFallback: (index) => `Day ${index + 1}`,
    fallbackCity: "Krasnodar"
  }
}

function t() {
  return props.language === "en" ? COPY.en : COPY.ru
}

function sendSuggestion(text) {
  if (typeof sendUserMessage === "function") {
    sendUserMessage(text)
  }
}

function formatTemp(value) {
  return typeof value === "number" ? `${value.toFixed(1)}°C` : "—"
}

function formatNumber(value, suffix = "") {
  return typeof value === "number" ? `${value}${suffix}` : "—"
}

function titleForLayout(copy) {
  if (props.title) return props.title
  if (props.layout === "current_compact") return copy.titles.current
  if (props.layout === "forecast_day") return copy.titles.forecastDay
  if (props.layout === "forecast_week") return copy.titles.forecastWeek
  if (props.layout === "forecast_dense") return copy.titles.forecastDense
  if (props.layout === "forecast_month") return copy.titles.forecastMonth
  if (props.layout === "history_compact") return copy.titles.history
  return copy.fallbackTitle
}

function sourceLabel(copy) {
  if (props.kind === "current") return copy.titles.current
  if (props.kind === "forecast") return copy.titles.forecastWeek
  if (props.kind === "history") return copy.titles.history
  return copy.fallbackTitle
}

function MiniStat({ label, value, icon: Icon }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/50 px-2.5 py-2">
      <div className="mb-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <Icon className="h-3 w-3" />
        <span>{label}</span>
      </div>
      <div className="text-sm font-medium text-foreground">{value}</div>
    </div>
  )
}

function CompactRow({ left, center, right, muted }) {
  return (
    <div className="grid grid-cols-[1.15fr_1fr_auto] items-center gap-3 border-b border-border/60 py-2 last:border-b-0">
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-foreground">{left}</div>
        {muted ? <div className="truncate text-[11px] text-muted-foreground">{muted}</div> : null}
      </div>
      <div className="truncate text-xs text-muted-foreground">{center}</div>
      <div className="text-xs font-medium text-foreground">{right}</div>
    </div>
  )
}

function Note() {
  if (!props.note) return null
  return <div className="text-[11px] text-muted-foreground">{props.note}</div>
}

function ActionRow() {
  const copy = t()
  if (!props.show_actions) return null

  const city = props.city || copy.fallbackCity

  if (props.kind === "current") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => sendSuggestion(copy.forecastPrompt(city))}>
          {copy.forecastAction}
        </Button>
        <Button size="sm" variant="outline" onClick={() => sendSuggestion(copy.umbrellaPrompt(city))}>
          {copy.umbrellaAction}
        </Button>
      </div>
    )
  }

  if (props.kind === "forecast") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => sendSuggestion(copy.comparePrompt(city))}>
          {copy.compareAction}
        </Button>
        <Button size="sm" variant="outline" onClick={() => sendSuggestion(copy.walkPrompt(city))}>
          {copy.walkAction}
        </Button>
      </div>
    )
  }

  if (props.kind === "history") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => sendSuggestion(copy.compareHistoryPrompt(city))}>
          {copy.compareHistoryAction}
        </Button>
      </div>
    )
  }

  return null
}

function CurrentCompact() {
  const copy = t()
  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-3xl font-semibold tracking-tight text-foreground">{formatTemp(props.temp_c)}</div>
          <div className="mt-1 text-sm text-muted-foreground">{props.condition || copy.currentFallback}</div>
        </div>
        <CloudSun className="h-7 w-7 text-primary" />
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <MiniStat label={copy.feels} value={formatTemp(props.feelslike_c)} icon={Thermometer} />
        <MiniStat label={copy.humidity} value={formatNumber(props.humidity, "%")} icon={Droplets} />
        <MiniStat label={copy.wind} value={formatNumber(props.wind_kph, copy.windUnit)} icon={Wind} />
        <MiniStat label={copy.pressure} value={formatNumber(props.pressure_mb, copy.pressureUnit)} icon={Gauge} />
      </div>

      <div className="text-[11px] text-muted-foreground">
        {copy.updatedPrefix}: {props.last_updated || "—"}
      </div>
    </div>
  )
}

function ForecastDayCompact() {
  const copy = t()
  const day = Array.isArray(props.forecast) ? props.forecast[0] : null
  if (!day) return null

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-foreground">{day.date || copy.dayFallback(0)}</div>
          <div className="mt-1 text-sm text-muted-foreground">{day.condition || copy.noDescription}</div>
        </div>
        <div className="text-right text-sm font-medium text-foreground">
          {formatTemp(day.mintemp_c)} / {formatTemp(day.maxtemp_c)}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <MiniStat label={copy.avg} value={formatTemp(day.avgtemp_c)} icon={Thermometer} />
        <MiniStat label={copy.rain} value={formatNumber(day.daily_chance_of_rain, "%")} icon={CloudRain} />
        <MiniStat label={copy.morning} value={formatTemp(day.morning_temp_c)} icon={Sunrise} />
        <MiniStat label={copy.evening} value={formatTemp(day.evening_temp_c)} icon={Sunset} />
      </div>
    </div>
  )
}

function ForecastWeekCompact() {
  const copy = t()
  const items = Array.isArray(props.forecast) ? props.forecast.slice(0, 7) : []

  return (
    <div className="space-y-1">
      {items.map((day, index) => (
        <CompactRow
          key={`${day.date || index}`}
          left={day.date || copy.dayFallback(index)}
          muted={day.condition || copy.noDescription}
          center={`${copy.rain} ${formatNumber(day.daily_chance_of_rain, "%")}`}
          right={`${formatTemp(day.mintemp_c)} / ${formatTemp(day.maxtemp_c)}`}
        />
      ))}
    </div>
  )
}

function ForecastDenseCompact() {
  const copy = t()
  const items = Array.isArray(props.forecast) ? props.forecast : []

  return (
    <div className="space-y-1">
      {items.map((day, index) => (
        <CompactRow
          key={`${day.date || index}`}
          left={day.date || copy.dayFallback(index)}
          muted={day.condition || copy.noDescription}
          center={`${copy.wind} ${formatNumber(day.maxwind_kph, copy.windUnit)}`}
          right={`${formatTemp(day.mintemp_c)} / ${formatTemp(day.maxtemp_c)}`}
        />
      ))}
    </div>
  )
}

function ForecastMonthCompact() {
  const copy = t()
  const items = Array.isArray(props.forecast) ? props.forecast : []

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {items.map((day, index) => (
        <div key={`${day.date || index}`} className="rounded-lg border border-border bg-secondary/40 px-2.5 py-2">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-xs font-medium text-foreground">{day.date || copy.dayFallback(index)}</div>
              <div className="truncate text-[11px] text-muted-foreground">{day.condition || copy.noDescription}</div>
            </div>
            <div className="text-[11px] font-medium text-foreground">
              {formatTemp(day.mintemp_c)} / {formatTemp(day.maxtemp_c)}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function HistoryCompact() {
  const copy = t()
  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-foreground">{props.date || copy.historyFallback}</div>
          <div className="mt-1 text-sm text-muted-foreground">{props.condition || copy.noDescription}</div>
        </div>
        <History className="h-6 w-6 text-primary" />
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <MiniStat label={copy.min} value={formatTemp(props.mintemp_c)} icon={Thermometer} />
        <MiniStat label={copy.max} value={formatTemp(props.maxtemp_c)} icon={Thermometer} />
        <MiniStat label={copy.avg} value={formatTemp(props.avgtemp_c)} icon={Thermometer} />
        <MiniStat label={copy.precip} value={formatNumber(props.totalprecip_mm, copy.precipUnit)} icon={CloudRain} />
      </div>
    </div>
  )
}

function Content() {
  if (props.layout === "current_compact") return <CurrentCompact />
  if (props.layout === "forecast_day") return <ForecastDayCompact />
  if (props.layout === "forecast_week") return <ForecastWeekCompact />
  if (props.layout === "forecast_dense") return <ForecastDenseCompact />
  if (props.layout === "forecast_month") return <ForecastMonthCompact />
  if (props.layout === "history_compact") return <HistoryCompact />
  return null
}

export default function WeatherSnippet() {
  const copy = t()
  const title = titleForLayout(copy)
  const source = sourceLabel(copy)
  const subtitle = props.city || copy.fallbackCity

  return (
    <Card className="mt-2 w-full border-border bg-card shadow-none">
      <CardHeader className="space-y-2 pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="border-border bg-secondary text-secondary-foreground">
            {source}
          </Badge>
          <Badge variant="outline" className="border-border bg-background text-foreground">
            <CalendarDays className="mr-1 h-3 w-3" />
            {subtitle}
          </Badge>
        </div>
        <CardTitle className="text-sm font-medium text-foreground">{title}</CardTitle>
        <Note />
      </CardHeader>
      <CardContent className="space-y-3 pt-1">
        <Content />
        <ActionRow />
      </CardContent>
    </Card>
  )
}
