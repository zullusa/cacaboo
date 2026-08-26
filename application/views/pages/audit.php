<?php extend('layouts/backend_layout'); ?>

<?php section('content'); ?>

<div class="container backend-page py-3" id="audit-page">
    <div class="row">
        <div class="col-sm-3">
            <?php component('settings_nav'); ?>
        </div>

        <div class="col-sm-9">
            <div class="row" id="audit">
                <div id="filter-audit" class="filter-records column col-12 mb-4">
                    <form class="mb-4">
                        <div class="input-group">
                            <input type="text" class="key form-control" aria-label="keyword">

                            <button class="filter btn btn-outline-secondary" type="submit"
                                    data-tippy-content="<?= lang('filter') ?>">
                                <i class="fas fa-search"></i>
                            </button>
                        </div>
                    </form>

                    <h4 class="mb-3 fw-light">
                        <?= lang('audit') ?>
                    </h4>

                    <div class="results overflow-auto" id="audit-results">
                        <!-- JS -->
                    </div>

                    <button id="load-more" class="btn btn-outline-secondary w-100 mt-3" style="display:none;">
                        <?= lang('load_more') ?>
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>

<?php end_section('content'); ?>

<?php section('scripts'); ?>

<script src="<?= asset_url('assets/js/http/audit_http_client.js') ?>"></script>
<script src="<?= asset_url('assets/js/pages/audit.js') ?>"></script>
<script>
    (function () {
        const $results = $('#audit-results');
        function resize() {
            const top = $results[0].getBoundingClientRect().top;
            const gap = 16;
            $results.css('max-height', Math.max(200, window.innerHeight - top - gap) + 'px');
        }
        resize();
        $(window).on('resize', resize);
    })();
</script>

<?php end_section('scripts'); ?>
