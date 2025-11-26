window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  delimiters: ['${', '}'],
  data: function () {
    return {
      settingsFormDialog: {
        show: false,
        data: {
          xero_client_id: null,
          xero_client_secret: null,
          xero_tax_standard: null,
          xero_tax_zero: null,
          xero_tax_exempt: null
        }
      },
      walletsFormDialog: {
        show: false,
        data: {
          wallet: null,
          push_payments: false,
          reconcile_name: null,
          reconcile_mode: null,
          xero_bank_account_id: null,
          tax_rate: null,
          notes: null
        }
      },
      walletsList: [],
      taxRateList: [
  { value: null,        label: 'Use Xero default for this account' },
  { value: 'standard',  label: 'Standard' },
  { value: 'zero',      label: 'Zero-rated (0%)' },
  { value: 'exempt',    label: 'Exempt / no tax' },
],
      accountCodeList: [
        {
          value: '200',
          label:
            '200 – Sales Revenue (Revenue from typical business operations)'
        },
        {
          value: '260',
          label: '260 – Other Revenue (Non-standard / one-off income)'
        },
        {value: '270', label: '270 – Interest Income'},
        {value: '310', label: '310 – Cost of Goods Sold'},
        {value: '320', label: '320 – Direct Wages'},
        {value: '321', label: '321 – Subcontractors'},
        {value: '325', label: '325 – Direct Expenses'},
        {value: '400', label: '400 – Advertising & Marketing'},
        {value: '401', label: '401 – Audit & Accountancy fees'},
        {value: '404', label: '404 – Bank Fees'},
        {value: '408', label: '408 – Cleaning'},
        {value: '412', label: '412 – Consulting'},
        {value: '416', label: '416 – Depreciation Expense'},
        {value: '418', label: '418 – Charitable and Political'},
        {value: '420', label: '420 – Entertainment-100% business'},
        {value: '424', label: '424 – Entertainment-0%'},
        {value: '425', label: '425 – Postage, Freight & Courier'},
        {value: '429', label: '429 – General Expenses'},
        {value: '433', label: '433 – Insurance'},
        {value: '437', label: '437 – Interest Paid'},
        {value: '441', label: '441 – Legal Expenses'},
        {value: '445', label: '445 – Light, Power, Heating'},
        {value: '449', label: '449 – Motor Vehicle Expenses'},
        {value: '457', label: '457 – Operating Lease Payments'},
        {value: '461', label: '461 – Printing & Stationery'},
        {value: '463', label: '463 – IT Software and Consumables'},
        {value: '465', label: '465 – Rates'},
        {value: '469', label: '469 – Rent'},
        {value: '473', label: '473 – Repairs & Maintenance'},
        {value: '477', label: '477 – Salaries'},
        {value: '478', label: "478 – Directors' Remuneration"},
        {value: '479', label: '479 – Employers National Insurance'},
        {value: '480', label: '480 – Staff Training'},
        {value: '482', label: '482 – Pensions Costs'},
        {value: '483', label: '483 – Medical Insurance'},
        {value: '485', label: '485 – Subscriptions'},
        {value: '489', label: '489 – Telephone & Internet'},
        {value: '493', label: '493 – Travel – National'},
        {value: '494', label: '494 – Travel – International'},
        {value: '500', label: '500 – Corporation Tax'},
        {value: '610', label: '610 – Accounts Receivable'},
        {value: '611', label: '611 – Provision for Doubtful Debts'},
        {value: '620', label: '620 – Prepayments'},
        {value: '630', label: '630 – Inventory'},
        {value: '710', label: '710 – Office Equipment'},
        {value: '711', label: '711 – Accum. Depreciation on Office Equipment'},
        {value: '720', label: '720 – Computer Equipment'},
        {
          value: '721',
          label: '721 – Accum. Depreciation on Computer Equipment'
        },
        {value: '740', label: '740 – Buildings'},
        {value: '741', label: '741 – Accum. Depreciation on Buildings'},
        {value: '750', label: '750 – Leasehold Improvements'},
        {
          value: '751',
          label: '751 – Accum. Depreciation on Leasehold Improvements'
        },
        {value: '760', label: '760 – Motor Vehicles'},
        {value: '761', label: '761 – Accum. Depreciation on Motor Vehicles'},
        {value: '764', label: '764 – Plant & Machinery'},
        {value: '765', label: '765 – Accum. Depreciation on Plant & Machinery'},
        {value: '770', label: '770 – Intangibles'},
        {value: '771', label: '771 – Accum. Amortisation on Intangibles'},
        {value: '800', label: '800 – Accounts Payable'},
        {value: '805', label: '805 – Accruals'},
        {value: '810', label: '810 – Income in Advance'},
        {value: '811', label: '811 – Credit Card Control Account'},
        {value: '814', label: '814 – Wages Payable - Payroll'},
        {value: '815', label: '815 – Employee Contribution to Benefits'},
        {value: '820', label: '820 – VAT'},
        {value: '825', label: '825 – PAYE Payable'},
        {value: '826', label: '826 – NIC Payable'},
        {value: '830', label: '830 – Provision for Corporation Tax'},
        {value: '835', label: "835 – Directors' Loan Account"},
        {value: '840', label: '840 – Historical Adjustment'},
        {value: '850', label: '850 – Suspense'},
        {value: '858', label: '858 – Pensions Payable'},
        {value: '860', label: '860 – Rounding'},
        {value: '868', label: '868 – Earnings Orders Payable'},
        {value: '877', label: '877 – Tracking Transfers'},
        {value: '900', label: '900 – Loan'},
        {value: '910', label: '910 – Hire Purchase Loan'},
        {value: '920', label: '920 – Deferred Tax'},
        {value: '947', label: '947 – Student Loan Deductions Payable'},
        {value: '950', label: '950 – Capital - Ordinary Shares'},
        {value: '960', label: '960 – Retained Earnings'},
        {value: '970', label: '970 – Owner A Funds Introduced'},
        {value: '980', label: '980 – Owner A Drawings'}
      ],
      walletsTable: {
        search: '',
        loading: false,
        columns: [
          {
            name: 'wallet',
            align: 'left',
            label: 'Wallet',
            field: 'wallet',
            sortable: true
          },
          {
            name: 'push_payments',
            align: 'left',
            label: 'Push payments',
            field: 'push_payments',
            sortable: true
          },
          {
            name: 'reconcile_name',
            align: 'left',
            label:
              'Auto-reconcile',
            field: 'reconcile_name',
            sortable: true
          },
          {
            name: 'reconcile_mode',
            align: 'left',
            label: 'Reconcile mode',
            field: 'reconcile_mode',
            sortable: true
          },
          {
            name: 'xero_bank_account_id',
            align: 'left',
            label:
              'Xero bank ID',
            field: 'xero_bank_account_id',
            sortable: true
          },
          {
            name: 'tax_rate',
            align: 'left',
            label: 'Tax rate',
            field: 'tax_rate',
            sortable: true
          },
          {
            name: 'last_synced',
            align: 'left',
            label: 'last_synced',
            field: 'last_synced',
            sortable: true
          },
          {
            name: 'status',
            align: 'left',
            label: 'status',
            field: 'status',
            sortable: true
          },
          {
            name: 'notes',
            align: 'left',
            label: 'Any notes',
            field: 'notes',
            sortable: true
          },
          {
            name: 'updated_at',
            align: 'left',
            label: 'Updated At',
            field: 'updated_at',
            sortable: true
          },
          {name: 'id', align: 'left', label: 'ID', field: 'id', sortable: true}
        ],
        pagination: {
          sortBy: 'updated_at',
          rowsPerPage: 10,
          page: 1,
          descending: true,
          rowsNumber: 10
        }
      }
    }
  },
  watch: {
    'walletsTable.search': {
      handler() {
        const props = {}
        if (this.walletsTable.search) {
          props['search'] = this.walletsTable.search
        }
        this.getWallets()
      }
    }
  },

  methods: {
    //////////////// Settings ////////////////////////
    async updateSettings() {
      try {
        const data = {...this.settingsFormDialog.data}

        await LNbits.api.request(
          'PUT',
          '/xero_sync/api/v1/settings',
          null,
          data
        )
        this.settingsFormDialog.show = false
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    async getSettings() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          '/xero_sync/api/v1/settings',
          null
        )
        this.settingsFormDialog.data = {
          ...this.settingsFormDialog.data,
          ...data
        }
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    async showSettingsDataForm() {
      await this.getSettings()
      this.settingsFormDialog.show = true
    },

    //////////////// Wallets ////////////////////////
    async showNewWalletsForm() {
      this.walletsFormDialog.data = {
        wallet: null,
        pull_payments: false,
        push_payments: true,
        reconcile_name: null,
        reconcile_mode: null,
        xero_bank_account_id: null,
        tax_rate: null,
        notes: null
      }
      this.walletsFormDialog.show = true
    },
    async showEditWalletsForm(data) {
      this.walletsFormDialog.data = {...data}
      this.walletsFormDialog.show = true
    },
    async saveWallets() {
      try {
        const data = {extra: {}, ...this.walletsFormDialog.data}
        const method = data.id ? 'PUT' : 'POST'
        const entry = data.id ? `/${data.id}` : ''
        await LNbits.api.request(
          method,
          '/xero_sync/api/v1/wallets' + entry,
          null,
          data
        )
        this.getWallets()
        this.walletsFormDialog.show = false
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },

    async getWallets(props) {
      try {
        this.walletsTable.loading = true
        const params = LNbits.utils.prepareFilterQuery(this.walletsTable, props)
        const {data} = await LNbits.api.request(
          'GET',
          `/xero_sync/api/v1/wallets/paginated?${params}`,
          null
        )
        this.walletsList = data.data
        this.walletsTable.pagination.rowsNumber = data.total
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.walletsTable.loading = false
      }
    },
    async deleteWallets(walletsId) {
      await LNbits.utils
        .confirmDialog('Are you sure you want to delete this Wallets?')
        .onOk(async () => {
          try {
            await LNbits.api.request(
              'DELETE',
              '/xero_sync/api/v1/wallets/' + walletsId,
              null
            )
            await this.getWallets()
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },
    async syncWallet(wallet) {
      await LNbits.utils
        .confirmDialog(
          'Push all current successful incoming payments for this wallet to Xero?'
        )
        .onOk(async () => {
          try {
            const {data} = await LNbits.api.request(
              'POST',
              `/xero_sync/api/v1/wallets/${wallet.id}/push`,
              null
            )
            LNbits.utils.notifySuccess(data.message || 'Wallet pushed to Xero')
            await this.getWallets()
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },
    async exportWalletsCSV() {
      await LNbits.utils.exportCSV(
        this.walletsTable.columns,
        this.walletsList,
        'wallets_' + new Date().toISOString().slice(0, 10) + '.csv'
      )
    },

    //////////////// Utils ////////////////////////
    dateFromNow(date) {
      return moment(date).fromNow()
    },
        async connectToXero() {
      try {
        const redirectUri = window.location.origin + '/xero_sync/oauth/callback'
        console.log(redirectUri)

        const scopes =
          'openid profile email accounting.settings accounting.transactions offline_access'
        const state = this.g.user && this.g.user.id
          ? this.g.user.id
          : 'xero_sync'

        const authUrl =
          'https://login.xero.com/identity/connect/authorize' +
          '?response_type=code' +
          '&client_id=' + encodeURIComponent(this.settingsFormDialog.data.xero_client_id) +
          '&redirect_uri=' + encodeURIComponent(redirectUri) +
          '&scope=' + encodeURIComponent(scopes) +
          '&state=' + encodeURIComponent(state)

        window.open(authUrl, '_blank')
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    }
  },
  async created() {
    this.getWallets()
    this.getSettings()
  }
})
