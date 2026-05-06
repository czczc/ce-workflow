import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'

export default createVuetify({
  theme: {
    defaultTheme: 'lightLab',
    themes: {
      lightLab: {
        dark: false,
        colors: {
          primary:      '#0e95a8',
          secondary:    '#0e95a8',
          warning:      '#c97a14',
          error:        '#d83a3a',
          success:      '#1f9d58',
          info:         '#2f6fda',
          background:   '#f4f5f7',
          surface:      '#ffffff',
          'on-surface': '#11161c',
        },
      },
      darkLab: {
        dark: true,
        colors: {
          primary:      '#4dd0e1',
          secondary:    '#4dd0e1',
          warning:      '#ffb454',
          error:        '#ff6b6b',
          success:      '#5fd38a',
          info:         '#6aa9ff',
          background:   '#0c1014',
          surface:      '#11161c',
          'on-surface': '#e7ecf2',
        },
      },
    },
  },
})
