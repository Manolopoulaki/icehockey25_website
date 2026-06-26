(function () {
  'use strict';

  var data = window.HOME_CHART_DATA;
  if (!data || typeof Chart === 'undefined') {
    return;
  }

  var rootStyles = getComputedStyle(document.documentElement);

  function cssVar(name, fallback) {
    var value = rootStyles.getPropertyValue(name).trim();
    return value || fallback;
  }

  var chartPalette = [
    cssVar('--color-primary', '#32A685'),
    cssVar('--color-secondary', '#17AEBF'),
    cssVar('--color-bright', '#F29D52'),
    cssVar('--color-accent', '#F2798F'),
  ];
  var currentUserColor = cssVar('--color-text', '#0D0D0D');
  var textColor = currentUserColor;

  Chart.defaults.color = textColor;
  Chart.defaults.borderColor = 'rgba(13, 13, 13, 0.12)';
  Chart.defaults.font.family = 'inherit';

  function lineColor(spec, paletteIndex) {
    if (spec.is_current_user) {
      return currentUserColor;
    }
    return chartPalette[paletteIndex % chartPalette.length];
  }

  function lineDataset(spec, paletteIndex) {
    var color = lineColor(spec, paletteIndex);
    return {
      label: spec.username,
      data: spec.data,
      borderColor: color,
      backgroundColor: color,
      borderWidth: spec.is_current_user ? 3 : 1.5,
      pointRadius: spec.is_current_user ? 4 : 2,
      tension: 0.2,
      fill: false,
    };
  }

  function mountLineChart(canvasId, labels, chartData, yTitle, chartOptions) {
    chartOptions = chartOptions || {};
    var invertY = !!chartOptions.invertY;
    var beginAtZero = chartOptions.beginAtZero !== undefined
      ? chartOptions.beginAtZero
      : !invertY;
    var canvas = document.getElementById(canvasId);
    if (!canvas || !labels || !labels.length || !chartData) {
      return;
    }
    var paletteIndex = 0;
    var datasets = (chartData.datasets || []).map(function (spec) {
      var dataset = lineDataset(spec, paletteIndex);
      if (!spec.is_current_user) {
        paletteIndex += 1;
      }
      return dataset;
    });
    if (!datasets.length) {
      return;
    }
    new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: datasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { boxWidth: 12, padding: 10 },
          },
        },
        scales: {
          x: {
            ticks: {
              maxTicksLimit: 12,
              autoSkip: true,
              maxRotation: 45,
              minRotation: 0,
            },
          },
          y: {
            reverse: invertY,
            beginAtZero: beginAtZero,
            grace: chartOptions.grace || '0%',
            title: { display: !!yTitle, text: yTitle || '' },
            ticks: invertY ? { stepSize: 1 } : {},
          },
        },
      },
    });
  }

  mountLineChart('chart-points-race', data.labels, data.points_race, 'Cumulative points', {
    beginAtZero: false,
    grace: '5%',
  });
  mountLineChart('chart-rank-over-time', data.labels, data.rank_over_time, 'Rank', {
    invertY: true,
  });
})();
