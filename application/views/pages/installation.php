<!doctype html>
<html lang="<?= config('language_code') ?>">
<head>
    <meta http-equiv="content-type" content="text/html; charset=UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">

    <title>Установка | CaCaBoo</title>

    <link rel="icon" type="image/x-icon" href="<?= asset_url('assets/img/favicon.ico') ?>">
    <link rel="stylesheet" type="text/css" href="<?= asset_url('assets/css/themes/default.css') ?>">
    <link rel="stylesheet" type="text/css" href="<?= asset_url('assets/css/general.css') ?>">
</head>
<body class="d-flex flex-column min-vh-100">

<div id="loading" class="position-fixed top-0 start-0 w-100 vh-100 d-flex justify-content-center align-items-center d-none bg-white">
    <img src="<?= base_url('assets/img/loading.gif') ?>" alt="loading">
</div>

<header class="bg-success-subtle mb-5">
    <div class="container">
        <div class="row">
            <div class="col-lg-9 offset-lg-1">
                <h1 class="text-dark-emphasis fw-light py-5">
                    Установка CaCaBoo
                </h1>
            </div>
        </div>    
    </div>
</header>

<div class="container flex-grow-1">
    <div class="row">
        <div class="col-lg-9 offset-lg-1">

            <div>
                <h3>Добро пожаловать на страницу установки CaCaBoo.</h3>

                <p class="text-break">
                    Эта страница поможет вам задать основные настройки вашей установки CaCaBoo. Вы сможете изменить
                    эти настройки и многие другие в панели администратора вашей системы. Не забудьте использовать
                    <strong class="text-primary">
                        <?= site_url('user/login') ?>
                    </strong>
                    адрес для входа в панель управления CaCaBoo.

                    Если у вас возникнут проблемы при использовании CaCaBoo, вы всегда можете обратиться к
                    <a href="https://sto-pitstop.ru">документации</a> и
                    <a href="https://groups.google.com/group/easy-appointments">группе поддержки</a> за помощью.
                    Вы также можете сообщить о проблемах на
                    <a href="https://github.com/alextselegidis/easyappointments/issues">GitHub Issues</a>,
                    чтобы помочь нашему процессу разработки.
                </p>
            </div>

            <div class="alert" hidden></div>

            <div class="row">
                <div class="admin-settings col-lg-6">
                    <h3 class="mb-3 fw-light">Администратор</h3>

                    <div class="mb-3">
                        <label class="form-label" for="first-name">
                            <?= lang('first_name') ?>
                            <span class="text-danger">*</span>
                        </label>
                        <input id="first-name" class="form-control required" maxlength="256">
                    </div>

                    <div class="mb-3">
                        <label class="form-label" for="last-name">
                            <?= lang('last_name') ?>
                            <span class="text-danger">*</span>
                        </label>
                        <input id="last-name" class="form-control required" maxlength="512">
                    </div>

                    <div class="mb-3">
                        <label class="form-label" for="email">
                            <?= lang('email') ?>
                            <span class="text-danger">*</span>
                        </label>
                        <input id="email" class="form-control required" maxlength="512">
                    </div>

                    <div class="mb-3">
                        <label class="form-label" for="username">
                            <?= lang('username') ?>
                            <span class="text-danger">*</span>
                        </label>
                        <input id="username" class="form-control required" maxlength="256">
                    </div>

                    <div class="mb-3">
                        <label class="form-label" for="password">
                            <?= lang('password') ?>
                            <span class="text-danger">*</span>
                        </label>
                        <input type="password" id="password" class="form-control required" maxlength="512">
                    </div>

                    <div class="mb-3">
                        <label class="form-label" for="password-confirm">
                            <?= lang('retype_password') ?>
                            <span class="text-danger">*</span>
                        </label>
                        <input type="password" id="password-confirm" class="form-control required" maxlength="512">
                    </div>

                </div>

                <div class="company-settings col-lg-6">
                    <h3 class="mb-3 fw-light"><?= lang('company') ?></h3>

                    <div class="mb-3">
                        <label class="form-label" for="company-name">
                            <?= lang('company_name') ?>
                            <span class="text-danger">*</span>
                        </label>
                        <input id="company-name" data-field="company_name" class="required form-control" value="STO Pitstop">
                        <div class="form-text text-muted">
                            <small>
                                <?= lang('company_name_hint') ?>
                            </small>
                        </div>
                    </div>

                    <div class="mb-3">
                        <label class="form-label" for="company-email">
                            <?= lang('company_email') ?>
                            <span class="text-danger">*</span>
                        </label>
                        <input id="company-email" data-field="company_email" class="required form-control">
                        <div class="form-text text-muted">
                            <small>
                                <?= lang('company_email_hint') ?>
                            </small>
                        </div>
                    </div>

                    <div class="mb-3">
                        <label class="form-label" for="company-link">
                            <?= lang('company_link') ?>
                            <span class="text-danger">*</span>
                        </label>
                        <input id="company-link" data-field="company_link" class="required form-control" value="https://sto-pitstop.ru">
                        <div class="form-text text-muted">
                            <small>
                                <?= lang('company_link_hint') ?>
                            </small>
                        </div>
                    </div>

                </div>
            </div>

            <p class="mb-5">
                Вы сможете настроить бизнес-логику на странице настроек панели управления после завершения установки.
                <br>
                Нажмите кнопку ниже, чтобы завершить процесс установки.
            </p>


            <button type="button" id="install" class="btn btn-primary mb-3">
                <i class="icon-white icon-ok me-2"></i>
                Установить CaCaBoo
            </button>
            
            
        </div>
    </div>

    
</div>

<footer class="bg-light mt-auto">
    <div class="container">
        <div class="row">
            <div class="col-lg-9 offset-lg-1 py-3">
                Работает на <a href="https://sto-pitstop.ru">CaCaBoo</a>
            </div>
        </div>
    </div>
    
</footer>

<?php component('js_vars_script'); ?>
<?php component('js_lang_script'); ?>

<script src="<?= asset_url('assets/vendor/jquery/jquery.min.js') ?>"></script>
<script src="<?= asset_url('assets/vendor/@popperjs-core/popper.min.js') ?>"></script>
<script src="<?= asset_url('assets/vendor/bootstrap/bootstrap.min.js') ?>"></script>

<script src="<?= asset_url('assets/js/app.js') ?>"></script>
<script src="<?= asset_url('assets/js/utils/message.js') ?>"></script>
<script src="<?= asset_url('assets/js/utils/validation.js') ?>"></script>
<script src="<?= asset_url('assets/js/utils/url.js') ?>"></script>
<script src="<?= asset_url('assets/js/pages/installation.js') ?>"></script>

</body>
</html>
