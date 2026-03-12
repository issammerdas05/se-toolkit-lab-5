import { useState, useEffect } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'
import { Bar, Line } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
)

const STORAGE_KEY = 'api_key'

interface ScoreBucket {
  bucket: string
  count: number
}

interface PassRate {
  task: string
  avg_score: number
  attempts: number
}

interface TimelineEntry {
  date: string
  submissions: number
}

interface Lab {
  id: number
  title: string
}

function getApiKey(): string {
  return localStorage.getItem(STORAGE_KEY) ?? ''
}

async function fetchWithAuth<T>(url: string): Promise<T> {
  const apiKey = getApiKey()
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export default function Dashboard() {
  const [labs, setLabs] = useState<Lab[]>([])
  const [selectedLab, setSelectedLab] = useState<string>('')
  const [scores, setScores] = useState<ScoreBucket[]>([])
  const [passRates, setPassRates] = useState<PassRate[]>([])
  const [timeline, setTimeline] = useState<TimelineEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchWithAuth<Lab[]>('/items/?type=lab')
      .then((data) => {
        setLabs(data)
        if (data.length > 0 && !selectedLab) {
          const firstLabId = `lab-${data[0].id}`
          setSelectedLab(firstLabId)
        }
      })
      .catch((err: Error) => {
        console.error('Failed to fetch labs:', err)
      })
  }, [])

  useEffect(() => {
    if (!selectedLab) return

    setLoading(true)
    setError(null)

    Promise.all([
      fetchWithAuth<ScoreBucket[]>(`/analytics/scores?lab=${selectedLab}`),
      fetchWithAuth<PassRate[]>(`/analytics/pass-rates?lab=${selectedLab}`),
      fetchWithAuth<TimelineEntry[]>(`/analytics/timeline?lab=${selectedLab}`),
    ])
      .then(([scoresData, passRatesData, timelineData]) => {
        setScores(scoresData)
        setPassRates(passRatesData)
        setTimeline(timelineData)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }, [selectedLab])

  const scoresChartData = {
    labels: scores.map((s) => s.bucket),
    datasets: [
      {
        label: 'Number of Students',
        data: scores.map((s) => s.count),
        backgroundColor: [
          'rgba(255, 99, 132, 0.6)',
          'rgba(255, 159, 64, 0.6)',
          'rgba(75, 192, 192, 0.6)',
          'rgba(54, 162, 235, 0.6)',
        ],
        borderColor: [
          'rgb(255, 99, 132)',
          'rgb(255, 159, 64)',
          'rgb(75, 192, 192)',
          'rgb(54, 162, 235)',
        ],
        borderWidth: 1,
      },
    ],
  }

  const timelineChartData = {
    labels: timeline.map((t) => t.date),
    datasets: [
      {
        label: 'Submissions',
        data: timeline.map((t) => t.submissions),
        borderColor: 'rgb(54, 162, 235)',
        backgroundColor: 'rgba(54, 162, 235, 0.5)',
        tension: 0.1,
        fill: true,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: 'Score Distribution',
      },
    },
  }

  const timelineOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: 'Submissions Over Time',
      },
    },
  }

  return (
    <div className="dashboard">
      <header className="app-header">
        <h1>Analytics Dashboard</h1>
      </header>

      <div className="lab-selector">
        <label htmlFor="lab-select">Select Lab: </label>
        <select
          id="lab-select"
          value={selectedLab}
          onChange={(e) => setSelectedLab(e.target.value)}
        >
          {labs.map((lab) => (
            <option key={lab.id} value={`lab-${lab.id}`}>
              {lab.title}
            </option>
          ))}
        </select>
      </div>

      {loading && <p>Loading analytics data...</p>}
      {error && <p className="error">Error: {error}</p>}

      {!loading && !error && (
        <div className="charts-container">
          <div className="chart-card">
            <Bar data={scoresChartData} options={chartOptions} />
          </div>

          <div className="chart-card">
            <Line data={timelineChartData} options={timelineOptions} />
          </div>

          <div className="chart-card pass-rates-table">
            <h2>Pass Rates by Task</h2>
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Avg Score</th>
                  <th>Attempts</th>
                </tr>
              </thead>
              <tbody>
                {passRates.map((rate) => (
                  <tr key={rate.task}>
                    <td>{rate.task}</td>
                    <td>{rate.avg_score}</td>
                    <td>{rate.attempts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
